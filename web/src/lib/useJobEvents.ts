/**
 * Subscribe to /api/jobs/:id/events.
 *
 * The server closes the stream on `end` (terminal stage) or `gone` (the job
 * row was deleted). EventSource reconnects on any close it did not ask for, so the
 * hook must close the socket itself on those frames -- otherwise a finished job
 * reopens the stream once a second, forever.
 *
 * Transport failures are different: a dropped wifi connection should reconnect.
 * After MAX_RETRIES consecutive failures the hook gives up and reports "lost",
 * and the caller falls back to polling the meeting endpoint.
 */
import { useEffect, useRef, useState } from "react";

import type { JobEvent } from "../types";

export type StreamStatus = "idle" | "connecting" | "live" | "ended" | "lost";

const MAX_RETRIES = 3;

export function useJobEvents(
  jobId: string | null | undefined,
  options: { enabled?: boolean; onEnd?: (event: JobEvent | null) => void } = {},
): { event: JobEvent | null; status: StreamStatus } {
  const { enabled = true, onEnd } = options;
  const [event, setEvent] = useState<JobEvent | null>(null);
  const [status, setStatus] = useState<StreamStatus>("idle");

  // Kept in a ref so a caller passing an inline callback does not tear the
  // stream down and rebuild it on every render.
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;

  useEffect(() => {
    if (!jobId || !enabled) {
      setStatus("idle");
      return;
    }

    const source = new EventSource(`/api/jobs/${jobId}/events`);
    let retries = 0;
    let finished = false;
    setStatus("connecting");

    const finish = (final: JobEvent | null, next: StreamStatus) => {
      finished = true;
      source.close();
      setStatus(next);
      onEndRef.current?.(final);
    };

    source.onopen = () => {
      retries = 0;
      setStatus("live");
    };

    source.addEventListener("job", (e) => {
      retries = 0;
      setStatus("live");
      setEvent(JSON.parse((e as MessageEvent).data) as JobEvent);
    });

    source.addEventListener("end", (e) => {
      const final = JSON.parse((e as MessageEvent).data) as JobEvent;
      setEvent(final);
      finish(final, "ended");
    });

    // The job row disappeared -- deleted from another tab, most likely.
    source.addEventListener("gone", () => finish(null, "ended"));

    source.onerror = () => {
      if (finished) return;
      // readyState CLOSED means EventSource has given up on its own.
      if (source.readyState === EventSource.CLOSED || ++retries > MAX_RETRIES) {
        finished = true;
        source.close();
        setStatus("lost");
        return;
      }
      setStatus("connecting");
    };

    return () => {
      finished = true;
      source.close();
    };
  }, [jobId, enabled]);

  return { event, status };
}

/** Seconds since `since`, ticking every second while `running`. */
export function useElapsed(since: string | null | undefined, running: boolean): number | null {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [running]);

  if (!since) return null;
  // The API stores UTC without a zone marker.
  const start = new Date(since.replace(" ", "T") + "Z").getTime();
  if (Number.isNaN(start)) return null;
  return Math.max(0, Math.floor((now - start) / 1000));
}
