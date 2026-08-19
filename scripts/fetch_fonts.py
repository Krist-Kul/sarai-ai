#!/usr/bin/env python3
"""Download Sarabun into sarai/docgen/fonts/ so the .docx can embed it.

The fonts are not committed: they are ~500 KB of binary that every clone would
carry, and the licence (OFL) is satisfied either way. Without them the document
still names Sarabun and renders correctly on any machine that has it installed;
with them it renders correctly everywhere.

    uv run python scripts/fetch_fonts.py

Source: the Google Fonts repository, which is where fonts.google.com serves
Sarabun from. Nothing else in the codebase reaches the network at build time.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/sarabun"
FILES = ("Sarabun-Regular.ttf", "Sarabun-Bold.ttf", "OFL.txt")
DEST = Path(__file__).resolve().parent.parent / "sarai" / "docgen" / "fonts"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = DEST / name
        if target.is_file():
            print(f"have  {target.relative_to(DEST.parent.parent.parent)}")
            continue
        url = f"{BASE}/{name}"
        print(f"fetch {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed host
                data = response.read()
        except OSError as exc:
            print(f"failed: {exc}", file=sys.stderr)
            return 1
        # A TTF starts with 0x00010000 or 'true'/'OTTO'; anything else means the
        # URL served an error page and writing it would break rendering later.
        if name.endswith(".ttf") and data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
            print(f"failed: {name} is not a TrueType file", file=sys.stderr)
            return 1
        target.write_bytes(data)
        print(f"wrote {target} ({len(data) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
