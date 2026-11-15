# Example: Thai House of Representatives question time

Minutes that Sarai AI generated from a recording of a session of the Thai House
of Representatives. They show what the pipeline produces on real, fast,
multi-speaker Thai speech.

| File | What it is |
|---|---|
| [`minutes.md`](minutes.md) | The same minutes as Markdown, so they can be read on GitHub |
| [`minutes.docx`](minutes.docx) | The Word document exactly as Sarai AI rendered it |

> [!WARNING]
> **Unedited machine output. This is not an official record.**
>
> Everything here was produced automatically: speech recognition, speaker
> separation and an LLM summary. No one has reviewed or corrected it. It
> **contains errors**: wrong words, wrong speaker attributions, and mistakes
> in the summary. Do not quote it, cite it, or rely on it as a statement of
> what anyone said, did or is accused of.
>
> Some statements recorded here are allegations made during a debate. They are
> not findings of fact. One of them, the remark about a Chaiyaphum MP, was
> **ordered withdrawn by the chair** during the session itself.
>
> For what was actually said, use the official record of the House of
> Representatives (บันทึกการประชุม / รายงานการประชุม) at
> [parliament.go.th](https://www.parliament.go.th).

> [!CAUTION]
> **คำเตือน:** เอกสารนี้สร้างขึ้นโดยอัตโนมัติด้วยระบบ AI (ถอดเสียง แยกผู้พูด และสรุปด้วย LLM)
> **ยังไม่ผ่านการตรวจทาน และมีข้อผิดพลาด** ทั้งคำผิด การระบุตัวผู้พูดผิด และการสรุปคลาดเคลื่อน
> **ไม่ใช่บันทึกการประชุมอย่างเป็นทางการ** ห้ามนำไปอ้างอิงว่าบุคคลใดกล่าวหรือกระทำการใด
> ข้อความที่เป็นการกล่าวหาในการอภิปรายเป็นเพียงข้อกล่าวหา ไม่ใช่ข้อเท็จจริง และคำพูดที่พาดพิง
> สส.จังหวัดชัยภูมิ ประธานในที่ประชุมได้วินิจฉัยให้ถอนแล้ว
> โปรดตรวจสอบจากบันทึกการประชุมอย่างเป็นทางการของสภาผู้แทนราษฎร

## Source

- **Recording:** [YouTube video `P0R4VxZq-JA`](https://www.youtube.com/watch?v=P0R4VxZq-JA&t=21s),
  published by Bright TV. All rights in the video belong to its owners.
- **This repository does not contain the audio or video.** Only the generated
  minutes are here, for research and to demonstrate the software, with the
  source credited. If you are a rights holder or a person named in these
  minutes and want them changed or removed, please open an issue.

## Known errors

Errors spotted at a glance. There are certainly others.

- The chair is labelled ประธานสภา (Speaker). The video title says the session
  was chaired by a deputy speaker (รองประธานสภา).
- A stray French word, `demande`, appears in the Discussion section. The LLM
  wrote it while summarizing.
- Attendees are listed by nickname as the speakers were labelled on the review
  screen. The roles were inferred by the LLM and are not verified.
- The meeting date is blank because it was not entered at upload.

## How it was made

| Stage | Setting |
|---|---|
| Speech recognition | `typhoon-ai/typhoon-whisper-turbo` (MLX build, Apple Silicon) |
| Speaker separation | `pyannote/speaker-diarization-community-1` |
| Summary | `deepseek-chat`, generated 2026-11-15 |

The speaker labels were assigned on the review screen. The minutes were then
generated and exported to `.docx` unchanged.
