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
    // Reset first: without it the box only ever grows.
    el.style.height = "0px";
    el.style.height = `${el.scrollHeight}px`;
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
      className={`w-full resize-none rounded-lg border border-transparent bg-transparent px-1.5 py-0.5 outline-none hover:border-line focus:border-brand-600 focus:bg-surface ${className}`}
    />
  );
}
