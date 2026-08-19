"""Embedding Sarabun into the .docx.

Thai renders as boxes on a machine without a Thai font installed, and the
people who open these minutes are not going to install one. Word's answer is an
embedded font: the TTF is stored inside the package as an obfuscated `.odttf`
part, listed in `word/fontTable.xml`, and switched on in `word/settings.xml`.

The obfuscation is not encryption -- it is a fixed XOR of the first 32 bytes
against a GUID, defined in ECMA-376 Part 1 §17.8.1, and exists so the file is
not a redistributable font. LibreOffice reads the same format.

python-docx has no API for any of this, so the three parts are edited directly.
Everything here is a no-op when the font files are absent: the document still
names Sarabun and renders correctly wherever it is installed.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from docx.document import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.package import OpcPackage
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from lxml import etree

log = logging.getLogger("sarai.docgen")

FONTS_DIR = Path(__file__).parent / "fonts"
FONT_NAME = "Sarabun"
ODTTF_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.obfuscatedFont"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W, "r": R}

# (element in fontTable, filename). Regular and bold are the two weights the
# renderer actually uses.
FACES: tuple[tuple[str, str], ...] = (
    ("embedRegular", "Sarabun-Regular.ttf"),
    ("embedBold", "Sarabun-Bold.ttf"),
)


def available_faces() -> list[tuple[str, Path]]:
    return [(tag, FONTS_DIR / name) for tag, name in FACES if (FONTS_DIR / name).is_file()]


def obfuscate(font_bytes: bytes, guid: uuid.UUID) -> bytes:
    """ECMA-376 font obfuscation: XOR the first 32 bytes with the GUID key.

    The key is the GUID's 16 bytes in reverse order, applied twice across the
    32-byte header. Applying the function again with the same GUID recovers the
    original file, which is what makes it round-trippable in a test.
    """
    key = guid.bytes_le[::-1]
    data = bytearray(font_bytes)
    for i in range(min(32, len(data))):
        data[i] ^= key[i % 16]
    return bytes(data)


def _enable_embedding(package: OpcPackage) -> None:
    """`w:embedTrueTypeFonts` in settings.xml -- without it Word ignores the
    embedded parts entirely and falls back to a substitute font."""
    settings = _find_part(package, "/word/settings.xml")
    if settings is None:
        return
    root = settings.element if hasattr(settings, "element") else etree.fromstring(settings.blob)
    if root.find(f"{{{W}}}embedTrueTypeFonts") is None:
        flag = etree.SubElement(root, f"{{{W}}}embedTrueTypeFonts")
        # Order matters in settings.xml; this element belongs near the top.
        root.remove(flag)
        root.insert(0, flag)


def _find_part(package: OpcPackage, partname: str) -> Part | None:
    for part in package.iter_parts():
        if str(part.partname) == partname:
            return part
    return None


def embed_fonts(document: Document) -> list[str]:
    """Embed whichever Sarabun faces are present. Returns the faces embedded."""
    faces = available_faces()
    if not faces:
        log.warning(
            "no Sarabun .ttf in %s; the .docx will name Sarabun but not carry it. "
            "Run scripts/fetch_fonts.py to add them.",
            FONTS_DIR,
        )
        return []

    package = document.part.package
    font_table = _find_part(package, "/word/fontTable.xml")
    if font_table is None:  # pragma: no cover - present in every template
        log.warning("this .docx template has no fontTable.xml; skipping font embedding")
        return []

    root = etree.fromstring(font_table.blob)
    font_el = root.find(f'{{{W}}}font[@{{{W}}}name="{FONT_NAME}"]')
    if font_el is None:
        font_el = etree.SubElement(root, f"{{{W}}}font")
        font_el.set(f"{{{W}}}name", FONT_NAME)
        charset = etree.SubElement(font_el, f"{{{W}}}charset")
        charset.set(f"{{{W}}}val", "DE")  # Thai
        family = etree.SubElement(font_el, f"{{{W}}}family")
        family.set(f"{{{W}}}val", "swiss")
        pitch = etree.SubElement(font_el, f"{{{W}}}pitch")
        pitch.set(f"{{{W}}}val", "variable")

    embedded: list[str] = []
    for index, (tag, path) in enumerate(faces, start=1):
        guid = uuid.uuid4()
        part = Part(
            PackURI(f"/word/fonts/font{index}.odttf"),
            ODTTF_CONTENT_TYPE,
            obfuscate(path.read_bytes(), guid),
            package,
        )
        # The relationship hangs off fontTable.xml, not the document part --
        # Word resolves r:id inside w:fonts against fontTable's own rels.
        rel_id = font_table.relate_to(part, RT.FONT)
        el = etree.SubElement(font_el, f"{{{W}}}{tag}")
        el.set(f"{{{R}}}id", rel_id)
        el.set(f"{{{W}}}fontKey", f"{{{str(guid).upper()}}}")
        embedded.append(tag)

    font_table._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    _enable_embedding(package)
    log.info("embedded %s into the document", ", ".join(embedded))
    return embedded
