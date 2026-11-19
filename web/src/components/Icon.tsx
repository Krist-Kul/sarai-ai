/**
 * Line icons exported from the Figma design system (24px grid, 1.8 stroke).
 *
 * The exported SVGs carry their light-theme stroke colour, so they are drawn
 * as a CSS mask filled with `currentColor`: geometry stays exactly as exported
 * and the colour follows the surrounding text, in either theme.
 *
 * Each SVG is exported at the size its slot uses in the design, so every entry
 * records that slot (`box`) and where the glyph sits inside it.
 */
import alert from "../assets/icons/alert.svg";
import arrowRight from "../assets/icons/arrow-right.svg";
import arrowRight14 from "../assets/icons/arrow-right-14.svg";
import check from "../assets/icons/check.svg";
import check14 from "../assets/icons/check-14.svg";
import clock from "../assets/icons/clock.svg";
import close12 from "../assets/icons/close-12.svg";
import close14 from "../assets/icons/close-14.svg";
import fileAudio24 from "../assets/icons/file-audio-24.svg";
import alert18 from "../assets/icons/alert-18.svg";
import check16 from "../assets/icons/check-16.svg";
import clock16 from "../assets/icons/clock-16.svg";
import clock20 from "../assets/icons/clock-20.svg";
import download16 from "../assets/icons/download-16.svg";
import sparkle14 from "../assets/icons/sparkle-14.svg";
import users16 from "../assets/icons/users-16.svg";
import plus14 from "../assets/icons/plus-14.svg";
import lock14 from "../assets/icons/lock-14.svg";
import pencil14 from "../assets/icons/pencil-14.svg";
import pencil18 from "../assets/icons/pencil-18.svg";
import pencil20 from "../assets/icons/pencil-20.svg";
import sparkle20 from "../assets/icons/sparkle-20.svg";
import upload20 from "../assets/icons/upload-20.svg";
import waveform20 from "../assets/icons/waveform-20.svg";
import pencil from "../assets/icons/pencil.svg";
import trash from "../assets/icons/trash.svg";
import upload from "../assets/icons/upload.svg";
import waveform from "../assets/icons/waveform.svg";

type Spec = { src: string; box: number; w: number; h: number; top: number; left: number };

const ICONS = {
  // 22px status-tile slot
  clock: { src: clock, box: 22, w: 18.15, h: 18.15, top: 1.925, left: 1.925 },
  waveform: { src: waveform, box: 22, w: 16.3167, h: 16.3167, top: 2.842, left: 2.842 },
  pencil: { src: pencil, box: 22, w: 15.4, h: 15.4, top: 3.758, left: 2.842 },
  check: { src: check, box: 22, w: 14.4833, h: 10.8167, top: 5.592, left: 3.758 },
  alert: { src: alert, box: 22, w: 18.15, h: 18.15, top: 1.925, left: 1.925 },
  // 16px button slot
  "arrow-right": { src: arrowRight, box: 16, w: 10.5333, h: 9.2, top: 3.4, left: 2.733 },
  upload: { src: upload, box: 16, w: 10.5333, h: 11.8667, top: 2.067, left: 2.733 },
  // 18px icon-button slot
  trash: { src: trash, box: 18, w: 13.35, h: 14.1, top: 2.29, left: 2.325 },
  // 14px inline slot (privacy note)
  lock: { src: lock14, box: 14, w: 9.21667, h: 10.3833, top: 1.808, left: 2.392 },
  "close-14": { src: close14, box: 14, w: 8.05, h: 8.05, top: 2.975, left: 2.975 },
  "arrow-right-14": { src: arrowRight14, box: 14, w: 9.21667, h: 8.05, top: 2.975, left: 2.392 },
  "check-14": { src: check14, box: 14, w: 9.21667, h: 6.88334, top: 3.558, left: 2.392 },
  "pencil-14": { src: pencil14, box: 14, w: 9.8, h: 9.8, top: 2.392, left: 1.808 },
  "pencil-18": { src: pencil18, box: 18, w: 12.6, h: 12.6, top: 3.075, left: 2.325 },
  "plus-14": { src: plus14, box: 14, w: 9.21667, h: 9.21667, top: 2.392, left: 2.392 },
  "sparkle-14": { src: sparkle14, box: 14, w: 10.3833, h: 10.9667, top: 1.517, left: 2.392 },
  // 16px inline / button slot
  download: { src: download16, box: 16, w: 10.5333, h: 11.8667, top: 2.067, left: 2.733 },
  "clock-16": { src: clock16, box: 16, w: 13.2, h: 13.2, top: 1.4, left: 1.4 },
  "users-16": { src: users16, box: 16, w: 13.205, h: 11.5333, top: 2.4, left: 1.4 },
  "check-16": { src: check16, box: 16, w: 10.5333, h: 7.86667, top: 4.067, left: 2.733 },
  "alert-18": { src: alert18, box: 18, w: 14.85, h: 14.85, top: 1.575, left: 1.575 },
  "clock-20": { src: clock20, box: 20, w: 16.5, h: 16.5, top: 1.75, left: 1.75 },
  // 12px chip-remove slot
  "close-12": { src: close12, box: 12, w: 6.9, h: 6.9, top: 2.55, left: 2.55 },
  // 24px dropzone file tile
  "file-audio-24": { src: fileAudio24, box: 24, w: 15.8, h: 19.8, top: 2.1, left: 4.1 },
  // 20px feature-card slot
  "upload-20": { src: upload20, box: 20, w: 13.1667, h: 14.8333, top: 2.583, left: 3.417 },
  "waveform-20": { src: waveform20, box: 20, w: 14.8333, h: 14.8333, top: 2.583, left: 2.583 },
  "pencil-20": { src: pencil20, box: 20, w: 14, h: 14, top: 3.417, left: 2.583 },
  "sparkle-20": { src: sparkle20, box: 20, w: 14.8333, h: 15.6667, top: 2.167, left: 3.417 },
} satisfies Record<string, Spec>;

export type IconName = keyof typeof ICONS;

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  const spec: Spec = ICONS[name];
  return (
    <span
      aria-hidden
      className={`relative inline-block shrink-0 ${className}`}
      style={{ width: spec.box, height: spec.box }}
    >
      <span
        className="absolute bg-current"
        style={{
          width: spec.w,
          height: spec.h,
          top: spec.top,
          left: spec.left,
          mask: `url("${spec.src}") center / 100% 100% no-repeat`,
          WebkitMask: `url("${spec.src}") center / 100% 100% no-repeat`,
        }}
      />
    </span>
  );
}
