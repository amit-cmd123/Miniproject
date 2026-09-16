/** The single place the frontend talks to the backend. */

import type {
  Accuracy,
  AnswerDetail,
  AnswerWithOCR,
  DocumentTranscription,
  OCRResult,
  PdfInspection,
  ProviderInfo,
  RoadmapPart,
  Thresholds,
} from "./types";

const BASE = "/api/v1";

/** An API failure carrying a message worth showing a user. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;

  let message = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    const detail = body?.detail ?? body?.message;
    if (typeof detail === "string") message = detail;
    else if (detail?.message) message = detail.message;
  } catch {
    /* a non-JSON error body is not worth surfacing verbatim */
  }
  throw new ApiError(message, response.status);
}

export const api = {
  async providerInfo(): Promise<ProviderInfo> {
    return unwrap(await fetch(`${BASE}/ocr/provider`));
  },

  async thresholds(): Promise<Thresholds> {
    return unwrap(await fetch(`${BASE}/config/thresholds`));
  },

  async roadmap(): Promise<{ parts: RoadmapPart[] }> {
    return unwrap(await fetch(`${BASE}/roadmap`));
  },

  async uploadAndTranscribe(file: File): Promise<AnswerWithOCR> {
    const form = new FormData();
    form.append("file", file);
    return unwrap(
      await fetch(`${BASE}/answers/transcribe`, { method: "POST", body: form }),
    );
  },

  /** How many pages, and roughly how long will reading them take? */
  async inspectPdf(file: File): Promise<PdfInspection> {
    const form = new FormData();
    form.append("file", file);
    return unwrap(
      await fetch(`${BASE}/documents/inspect`, { method: "POST", body: form }),
    );
  },

  async transcribeDocument(
    file: File,
    pages?: string,
  ): Promise<DocumentTranscription> {
    const form = new FormData();
    form.append("file", file);
    if (pages?.trim()) form.append("pages", pages.trim());
    return unwrap(
      await fetch(`${BASE}/documents/transcribe`, { method: "POST", body: form }),
    );
  },

  async listAnswers(): Promise<AnswerDetail[]> {
    return unwrap(await fetch(`${BASE}/answers`));
  },

  async getAnswer(id: string): Promise<AnswerDetail> {
    return unwrap(await fetch(`${BASE}/answers/${id}`));
  },

  async correct(id: string, correctedText: string): Promise<OCRResult> {
    return unwrap(
      await fetch(`${BASE}/answers/${id}/ocr/verify`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrected_text: correctedText }),
      }),
    );
  },

  async accuracy(id: string, referenceText: string): Promise<Accuracy> {
    return unwrap(
      await fetch(`${BASE}/answers/${id}/ocr/accuracy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reference_text: referenceText }),
      }),
    );
  },

  imageUrl(id: string): string {
    return `${BASE}/answers/${id}/image`;
  },

  segmentationUrl(id: string): string {
    return `${BASE}/answers/${id}/segmentation`;
  },
};
