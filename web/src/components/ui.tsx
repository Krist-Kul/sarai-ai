/**
 * Primitives from the Figma "Components" page. Pages compose these rather than
 * restyling buttons and cards inline, so the system stays one system.
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { useI18n } from "../lib/i18n";
import type { StageKind } from "../lib/stage";
import { Icon, type IconName } from "./Icon";

// --- Button -----------------------------------------------------------------

export type ButtonVariant = "primary" | "solid" | "outline" | "ghost" | "danger";
type ButtonSize = "md" | "sm";

const VARIANT: Record<ButtonVariant, string> = {
  // One per screen. The halo on hover is the design's glow-brand effect.
  primary: "bg-brand text-on-brand hover:shadow-glow",
  // Opens a finished result.
  solid: "bg-ink text-on-ink hover:bg-ink/90",
  outline: "border border-line-control bg-surface text-ink hover:bg-surface-raised",
  ghost: "text-ink-muted hover:bg-surface-raised hover:text-ink",
  danger: "bg-danger text-on-brand hover:bg-danger/90",
};

const SIZE: Record<ButtonSize, string> = {
  md: "h-10 px-5 text-label",
  sm: "h-8 px-4 text-small-strong",
};

export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md"): string {
  return (
    "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap " +
    "rounded-full transition-[box-shadow,background-color] focus-visible:outline-2 " +
    "focus-visible:outline-offset-2 focus-visible:outline-brand " +
    "disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none " +
    `${VARIANT[variant]} ${SIZE[size]}`
  );
}

type Common = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  children: ReactNode;
  className?: string;
};

export function Button({
  variant,
  size,
  icon,
  children,
  className = "",
  type = "button",
  ...rest
}: Common & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type={type} className={`${buttonClass(variant, size)} ${className}`} {...rest}>
      {children}
      {icon && <Icon name={icon} />}
    </button>
  );
}

export function ButtonLink({
  variant,
  size,
  icon,
  children,
  className = "",
  ...rest
}: Common & LinkProps) {
  return (
    <Link className={`${buttonClass(variant, size)} ${className}`} {...rest}>
      {children}
      {icon && <Icon name={icon} />}
    </Link>
  );
}

/** Round 32px icon button; destructive hover by default (it is the delete). */
export function IconButton({
  icon,
  label,
  className = "",
  ...rest
}: { icon: IconName; label: string } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full text-ink-subtle hover:bg-danger-soft hover:text-danger ${className}`}
      {...rest}
    >
      <Icon name={icon} />
    </button>
  );
}

// --- Card -------------------------------------------------------------------

export function Card({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "li";
}) {
  return (
    <Tag className={`rounded-lg border border-line bg-surface shadow-card ${className}`}>
      {children}
    </Tag>
  );
}

// --- Status -----------------------------------------------------------------

const TILE: Record<StageKind, { className: string; icon: IconName }> = {
  queued: { className: "bg-surface-raised text-ink-subtle", icon: "clock" },
  running: { className: "bg-live-soft text-live", icon: "waveform" },
  review: { className: "bg-brand text-on-brand", icon: "pencil" },
  done: { className: "bg-done-soft text-done", icon: "check" },
  failed: { className: "bg-danger-soft text-danger", icon: "alert" },
};

/** Leading status tile: 44px (MD) / 36px (SM). */
export function StatusTile({ kind, size = "md" }: { kind: StageKind; size?: "md" | "sm" }) {
  const tile = TILE[kind];
  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center ${
        size === "md" ? "size-11 rounded-md" : "size-9 rounded-sm"
      } ${tile.className}`}
    >
      <Icon name={tile.icon} />
    </span>
  );
}

export function PulseDot({ className = "bg-live" }: { className?: string }) {
  return <span aria-hidden className={`pulse-dot size-1.5 shrink-0 rounded-full ${className}`} />;
}

/** Live progress bar; `value` is 0..1. */
export function Progress({ value, className = "" }: { value: number; className?: string }) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div
        className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-raised"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-live transition-[width] duration-500"
          style={{
            width: `${percent}%`,
            backgroundImage:
              "linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.35) 50%, rgba(255,255,255,0) 100%)",
          }}
        />
      </div>
      <span className="text-data text-ink-muted">{percent}%</span>
    </div>
  );
}

// --- Notice -----------------------------------------------------------------

const NOTICE = {
  live: "bg-live-soft text-live",
  danger: "bg-danger-soft text-danger",
  review: "bg-brand-soft text-brand-ink",
} as const;

/** Full-width notice bar. `inline` drops the bar edge for use inside a page. */
export function Notice({
  tone,
  children,
  inline = false,
  action,
}: {
  tone: keyof typeof NOTICE;
  children: ReactNode;
  inline?: boolean;
  action?: ReactNode;
}) {
  return (
    <div
      className={`flex items-center gap-2.5 text-small ${NOTICE[tone]} ${
        inline ? "rounded-md px-4 py-3" : "min-h-11 border-b border-line px-6 py-2.5"
      }`}
    >
      {tone === "live" ? (
        <PulseDot className="bg-current" />
      ) : (
        <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-current" />
      )}
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

// --- Brand ------------------------------------------------------------------

/** Indigo→cyan glyph with a 4-bar waveform + "Sarai AI" wordmark. */
export function Mark() {
  return (
    <span className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="flex size-[30px] items-center justify-center gap-0.5 rounded-sm shadow-[0_4px_12px_-2px_rgba(79,70,229,0.28)]"
        style={{ backgroundImage: "linear-gradient(135deg, #4f46e5 25%, #06b6d4 75%)" }}
      >
        {[8, 16, 11, 6].map((h, i) => (
          <span key={i} className="w-[3px] rounded-[2px] bg-white" style={{ height: h }} />
        ))}
      </span>
      <span className="whitespace-nowrap font-brand text-[17px] font-bold tracking-[-0.17px] text-ink">
        Sarai <span className="text-brand-ink">AI</span>
      </span>
    </span>
  );
}

// --- Page head --------------------------------------------------------------

export function PageHead({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {eyebrow && <p className="text-eyebrow text-ink-subtle">{eyebrow}</p>}
        <h1 className="text-[24px] leading-[34px] font-semibold tracking-[-0.3px] sm:text-display">
          {title}
        </h1>
        {subtitle && <p className="text-small text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** "← back" link above a page head. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex w-fit items-center gap-1.5 text-small text-ink-muted hover:text-ink"
    >
      <Icon name="arrow-right-14" className="rotate-180" />
      {children}
    </Link>
  );
}

/** The privacy line. Sits under every upload; never decorate it away. */
export function PrivacyNote() {
  const { t } = useI18n();
  return (
    <p className="flex items-center gap-1.5 text-small text-ink-muted">
      <Icon name="lock" className="text-brand" />
      {t("privacyNote")}
    </p>
  );
}
