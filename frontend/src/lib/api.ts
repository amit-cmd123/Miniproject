/** The single place the frontend talks to the backend. */

import type {
  Accuracy,
  Analytics,
  AnswerDetail,
  AnswerKeyRecord,
  AnswerWithOCR,
  BookletResult,
  BookletSegmentation,
  ConfidenceWeights,
  DocumentTranscription,
  Engine,
  Engines,
  Evaluation,
  EvaluatorInfo,
  Exam,
  ExamDetail,
  OCRResult,
  ParsedPaper,
  PdfInspection,
  ProviderInfo,
  Question,
  QuestionDraft,
  QuestionPatch,
  Review,
  RoadmapPart,
  Rubric,
  RubricDraft,
  RubricValidation,
  RubricVersion,
  Thresholds,
} from "./types";

const BASE = "/api/v1";

/** `?engine=` for the calls that can run on either engine.
 *
 * Omitted entirely when no engine is given, so the backend applies whatever
 * the .env file configures rather than the interface quietly deciding.
 */
function withEngine(path: string, engine?: Engine): string {
  if (!engine) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}engine=${engine}`;
}

/** An API failure carrying a message worth showing a user. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function json<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH",
  body: unknown,
): Promise<T> {
  return unwrap(
    await fetch(`${BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
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
  async providerInfo(engine?: Engine): Promise<ProviderInfo> {
    return unwrap(await fetch(`${BASE}${withEngine("/ocr/provider", engine)}`));
  },

  /** Which engines exist here, and whether each can run right now. */
  async engines(): Promise<Engines> {
    return unwrap(await fetch(`${BASE}/engines`));
  },

  async thresholds(): Promise<Thresholds> {
    return unwrap(await fetch(`${BASE}/config/thresholds`));
  },

  async roadmap(): Promise<{ parts: RoadmapPart[] }> {
    return unwrap(await fetch(`${BASE}/roadmap`));
  },

  async uploadAndTranscribe(file: File, engine?: Engine): Promise<AnswerWithOCR> {
    const form = new FormData();
    form.append("file", file);
    return unwrap(
      await fetch(`${BASE}${withEngine("/answers/transcribe", engine)}`, {
        method: "POST",
        body: form,
      }),
    );
  },

  /** How many pages, and roughly how long will reading them take? */
  async inspectPdf(file: File, engine?: Engine): Promise<PdfInspection> {
    const form = new FormData();
    form.append("file", file);
    return unwrap(
      await fetch(`${BASE}${withEngine("/documents/inspect", engine)}`, {
        method: "POST",
        body: form,
      }),
    );
  },

  async transcribeDocument(
    file: File,
    pages?: string,
    engine?: Engine,
  ): Promise<DocumentTranscription> {
    const form = new FormData();
    form.append("file", file);
    if (pages?.trim()) form.append("pages", pages.trim());
    return unwrap(
      await fetch(`${BASE}${withEngine("/documents/transcribe", engine)}`, {
        method: "POST",
        body: form,
      }),
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

  /* ---- Part 2: questions and rubrics ---- */

  async exams(): Promise<Exam[]> {
    return unwrap(await fetch(`${BASE}/exams`));
  },

  async exam(id: string): Promise<ExamDetail> {
    return unwrap(await fetch(`${BASE}/exams/${id}`));
  },

  /** Start an empty paper. Questions and rubrics are added to it afterwards. */
  async createExam(payload: {
    title: string;
    subject: string;
    subject_code?: string | null;
    term?: string | null;
  }): Promise<ExamDetail> {
    return json(`/exams`, "POST", { ...payload, questions: [] });
  },

  /** Load the bundled paper. Idempotent, so it is safe to call on open. */
  async seedExam(replace = false): Promise<ExamDetail> {
    return unwrap(
      await fetch(`${BASE}/exams/seed?replace=${replace}`, { method: "POST" }),
    );
  },

  async validateExam(id: string): Promise<RubricValidation> {
    return unwrap(await fetch(`${BASE}/exams/${id}/validate`));
  },

  async questions(examId?: string): Promise<Question[]> {
    const query = examId ? `?exam_id=${examId}&include_rubric=true` : "?include_rubric=true";
    return unwrap(await fetch(`${BASE}/questions${query}`));
  },

  async rubric(questionId: string): Promise<Rubric> {
    return unwrap(await fetch(`${BASE}/questions/${questionId}/rubric`));
  },

  /* ---- Part 2: editing the paper ----
   *
   * A rubric is never mutated in place: `saveRubric` writes a new version and
   * retires the previous one, so a score awarded last term still resolves to
   * the rubric it was actually marked against. The same is true of answer
   * keys. That is why these are PUTs that return a new version number rather
   * than PATCHes.
   */

  async addQuestion(examId: string, draft: QuestionDraft): Promise<Question> {
    return json(`/exams/${examId}/questions`, "POST", draft);
  },

  async updateQuestion(questionId: string, patch: QuestionPatch): Promise<Question> {
    return json(`/questions/${questionId}`, "PATCH", patch);
  },

  async deleteQuestion(questionId: string): Promise<void> {
    const response = await fetch(`${BASE}/questions/${questionId}`, {
      method: "DELETE",
    });
    if (!response.ok) await unwrap(response);
  },

  /** Writes a NEW rubric version. The old one is kept, deactivated. */
  async saveRubric(questionId: string, draft: RubricDraft): Promise<Rubric> {
    return json(`/questions/${questionId}/rubric`, "PUT", draft);
  },

  async rubricVersions(questionId: string): Promise<RubricVersion[]> {
    return unwrap(await fetch(`${BASE}/questions/${questionId}/rubric/versions`));
  },

  async answerKey(questionId: string): Promise<AnswerKeyRecord> {
    return unwrap(await fetch(`${BASE}/questions/${questionId}/answer-key`));
  },

  /** Writes a NEW answer-key version. */
  async saveAnswerKey(
    questionId: string,
    referenceAnswer: string,
  ): Promise<AnswerKeyRecord> {
    return json(`/questions/${questionId}/answer-key`, "PUT", {
      reference_answer: referenceAnswer,
    });
  },

  /** The paper as seed JSON, in the same shape `data/exam/seed_exam.json` uses. */
  async exportExam(examId: string): Promise<Record<string, unknown>> {
    return unwrap(await fetch(`${BASE}/exams/${examId}/export`));
  },

  async importExam(document: unknown): Promise<ExamDetail> {
    return json(`/exams/import`, "POST", document);
  },

  /** Read a typed question paper (.docx / .pdf / .txt) and propose a paper.
   *
   * Nothing is saved by this call. What comes back is a proposal shown to the
   * examiner, who edits it and then commits it through `importExam` - the
   * same door a hand-written paper goes through.
   */
  async parseDocument(file: File, engine?: Engine): Promise<ParsedPaper> {
    const form = new FormData();
    form.append("file", file);
    return unwrap(
      await fetch(`${BASE}${withEngine("/exams/parse-document", engine)}`, {
        method: "POST",
        body: form,
      }),
    );
  },

  async deleteExam(examId: string): Promise<void> {
    const response = await fetch(`${BASE}/exams/${examId}`, { method: "DELETE" });
    if (!response.ok) await unwrap(response);
  },

  /* ---- Part 3: evaluation ---- */

  async evaluatorInfo(engine?: Engine): Promise<EvaluatorInfo> {
    return unwrap(
      await fetch(`${BASE}${withEngine("/evaluations/provider", engine)}`),
    );
  },

  async confidenceWeights(): Promise<ConfidenceWeights> {
    return unwrap(await fetch(`${BASE}/config/confidence-weights`));
  },

  async evaluate(
    answerId: string,
    questionId?: string,
    samples?: number,
    engine?: Engine,
  ): Promise<Evaluation> {
    return json(withEngine("/evaluations", engine), "POST", {
      answer_id: answerId,
      question_id: questionId,
      samples,
    });
  },

  async evaluation(id: string): Promise<Evaluation> {
    return unwrap(await fetch(`${BASE}/evaluations/${id}`));
  },

  /** The marking queue: latest evaluation per answer, optionally filtered. */
  async evaluations(
    filters: { needsReview?: boolean; unreviewed?: boolean } = {},
  ): Promise<Evaluation[]> {
    const query = new URLSearchParams();
    if (filters.needsReview) query.set("needs_review", "true");
    if (filters.unreviewed) query.set("unreviewed", "true");
    const suffix = query.toString() ? `?${query}` : "";
    return unwrap(await fetch(`${BASE}/evaluations${suffix}`));
  },

  async answerEvaluations(answerId: string): Promise<Evaluation[]> {
    return unwrap(await fetch(`${BASE}/answers/${answerId}/evaluations`));
  },

  /** Where each question's answer sits in a booklet, without marking it. */
  async segmentation(documentRef: string, examId?: string): Promise<BookletSegmentation> {
    const query = examId ? `?exam_id=${examId}` : "";
    return unwrap(await fetch(`${BASE}/documents/${documentRef}/segmentation${query}`));
  },

  async evaluateBooklet(
    documentRef: string,
    options: {
      examId?: string;
      bookletRef?: string;
      samples?: number;
      engine?: Engine;
    } = {},
  ): Promise<BookletResult> {
    return json(withEngine("/documents/evaluate", options.engine), "POST", {
      document_ref: documentRef,
      exam_id: options.examId,
      booklet_ref: options.bookletRef,
      samples: options.samples,
    });
  },

  /* ---- Part 4: review and validation ---- */

  async review(payload: {
    evaluationId: string;
    action: "accept" | "modify";
    finalScore?: number;
    comments?: string;
    durationMs?: number;
  }): Promise<Review> {
    return json("/reviews", "POST", {
      evaluation_id: payload.evaluationId,
      action: payload.action,
      final_score: payload.finalScore,
      comments: payload.comments,
      duration_ms: payload.durationMs ?? 0,
    });
  },

  async reviews(evaluationId: string): Promise<Review[]> {
    return unwrap(await fetch(`${BASE}/evaluations/${evaluationId}/reviews`));
  },

  async analytics(): Promise<Analytics> {
    return unwrap(await fetch(`${BASE}/analytics/summary`));
  },
};
