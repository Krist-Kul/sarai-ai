/**
 * Debounced autosave.
 *
 * The review and minutes screens are text editors: the user types, and the
 * server holds the only copy. Saving every keystroke hammers the API, saving
 * only on blur loses work when a tab closes mid-sentence. This saves shortly
 * after typing stops, exposes the state for a status line, and blocks the tab
 * from closing while a save is still owed.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

export function useDebouncedSave<T>(
  save: (value: T) => Promise<unknown>,
  delay = 900,
): {
  status: SaveStatus;
  error: string | null;
  schedule: (value: T) => void;
  flush: () => void;
} {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const timer = useRef<number | undefined>(undefined);
  const pending = useRef<{ value: T } | null>(null);
  const inFlight = useRef(false);
  // Kept in a ref so a caller passing an inline closure does not restart the
  // timer on every render.
  const saveRef = useRef(save);
  saveRef.current = save;

  const run = useCallback(async () => {
    if (inFlight.current || pending.current === null) return;
    const { value } = pending.current;
    pending.current = null;
    inFlight.current = true;
    setStatus("saving");
    try {
      await saveRef.current(value);
      setError(null);
      // Another edit landed while this save was in flight; go again.
      setStatus(pending.current === null ? "saved" : "dirty");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    } finally {
      inFlight.current = false;
      if (pending.current !== null) void run();
    }
  }, []);

  const flush = useCallback(() => {
    window.clearTimeout(timer.current);
    void run();
  }, [run]);

  const schedule = useCallback(
    (value: T) => {
      pending.current = { value };
      setStatus("dirty");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void run(), delay);
    },
    [delay, run],
  );

  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    if (status !== "dirty" && status !== "saving") return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [status]);

  return { status, error, schedule, flush };
}
