import { useEffect, useRef } from "react";

/**
 * A textarea that grows with its content, so an edited paragraph reads as part
 * of the document rather than as a form field with a scrollbar.
 */
export function EditableText({
  value,
  onChange,
  onCommit,
  onFocus,
  placeholder,
  className = "",
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  onCommit?: () => void;
  onFocus?: () => void;
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      // Reset first: without it the box only ever grows.
      el.style.height = "0px";
      el.style.height = `${el.scrollHeight}px`;
    };
    fit();
    // A measurement taken before the web font arrives, or at another width,
    // leaves blank lines under the text; measure again when either changes.
    let alive = true;
    void document.fonts?.ready.then(() => alive && fit());
    const observer = new ResizeObserver(fit);
    observer.observe(el.parentElement ?? el);
    return () => {
      alive = false;
      observer.disconnect();
    };
  }, [value]);

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onCommit}
      onFocus={onFocus}
      placeholder={placeholder}
      aria-label={ariaLabel}
      rows={1}
      className={`w-full resize-none rounded-sm border border-transparent bg-transparent px-2 py-0.5 text-ink outline-none hover:bg-surface-raised focus:border-brand focus:bg-surface-raised ${className}`}
    />
  );
}
