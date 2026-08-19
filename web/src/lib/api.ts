/**
 * Thin fetch wrapper. Types come from ../types.ts, which is generated from the
 * Pydantic models -- if the backend contract changes, this file stops compiling.
 */
import type {
  Attendee,
  HealthResponse,
  LanguageHint,
  MeetingCreated,
  MeetingDetail,
  MeetingListItem,
  MinutesJSON,
  Segment,
  SummaryResponse,
  TranscriptResponse,
} from "../types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<never> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail) && body.detail.length > 0) {
      // FastAPI validation errors arrive as a list of {loc, msg}.
      detail = body.detail
        .map((e) => (typeof e === "object" && e && "msg" in e ? String(e.msg) : String(e)))
        .join("; ");
    }
  } catch {
    /* response had no JSON body; the status line is the best we have */
  }
  throw new ApiError(detail, res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  listMeetings: () => request<MeetingListItem[]>("/api/meetings"),
  getMeeting: (id: string) => request<MeetingDetail>(`/api/meetings/${id}`),
  deleteMeeting: (id: string) =>
    request<void>(`/api/meetings/${id}`, { method: "DELETE" }),
  audioUrl: (id: string) => `/api/meetings/${id}/audio`,

  // --- review ---
  getTranscript: (id: string) => request<TranscriptResponse>(`/api/meetings/${id}/transcript`),
  saveTranscript: (id: string, segments: Segment[]) =>
    request<TranscriptResponse>(`/api/meetings/${id}/transcript`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ segments }),
    }),
  saveSpeakers: (id: string, speakers: Record<string, string>) =>
    request<Record<string, string>>(`/api/meetings/${id}/speakers`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ speakers }),
    }),

  // --- minutes ---
  summarize: (id: string) =>
    request<MeetingCreated>(`/api/meetings/${id}/summarize`, { method: "POST" }),
  getSummary: (id: string) => request<SummaryResponse>(`/api/meetings/${id}/summary`),
  saveSummary: (id: string, minutes: MinutesJSON) =>
    request<SummaryResponse>(`/api/meetings/${id}/summary`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(minutes),
    }),
  documentUrl: (id: string) => `/api/meetings/${id}/document`,

  createMeeting: (input: {
    file: File;
    title: string;
    meetingDate?: string;
    languageHint: LanguageHint;
    attendees: Attendee[];
    glossary: string[];
    onProgress?: (fraction: number) => void;
  }): Promise<MeetingCreated> => {
    const form = new FormData();
    form.append("file", input.file);
    form.append("title", input.title);
    if (input.meetingDate) form.append("meeting_date", input.meetingDate);
    form.append("language_hint", input.languageHint);
    for (const a of input.attendees) form.append("attendees", JSON.stringify(a));
    for (const g of input.glossary) form.append("glossary", g);

    // XHR rather than fetch: uploads are up to 500 MB and the user needs a
    // progress bar, which fetch still cannot give us for request bodies.
    return new Promise<MeetingCreated>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/meetings");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) input.onProgress?.(e.loaded / e.total);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText) as MeetingCreated);
          return;
        }
        let detail = `${xhr.status} ${xhr.statusText}`;
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: unknown };
          if (typeof body.detail === "string") detail = body.detail;
          else if (Array.isArray(body.detail))
            detail = body.detail
              .map((e) =>
                typeof e === "object" && e && "msg" in e
                  ? String((e as { msg: unknown }).msg)
                  : String(e),
              )
              .join("; ");
        } catch {
          /* keep the status line */
        }
        reject(new ApiError(detail, xhr.status));
      };
      xhr.onerror = () => reject(new ApiError("Network error during upload", 0));
      xhr.send(form);
    });
  },
};
