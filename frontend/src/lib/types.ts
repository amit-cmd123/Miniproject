/**
 * Types mirroring the backend Pydantic schemas.
 *
 * Kept by hand for Phase 1. Phase 2 generates these from the OpenAPI document
 * so the two can never drift; the shapes below are already the generated ones.
 */

export type TranscriptionBand = "reliable" | "spot_check" | "verify" | "unusable";

export type AnswerStatus =
  | "registered"
  | "ocr_running"
  | "ocr_done"
  | "ocr_failed"
  | "evaluated"
  | "under_review"
  | "finalized";

export interface LineResult {
  index: number;
  text: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface PreprocessingReport {
  steps: string[];
  original_size: [number, number] | null;
  processed_size: [number, number] | null;
  deskew_angle_deg: number;
  estimated_ink_coverage: number;
  detected_lines: number;
  blur_score: number;
  is_low_contrast: boolean;
}

export interface OCRResult {
  id: string;
  answer_id: string;
  extracted_text: string;
  corrected_text: string | null;
  effective_text: string;
  text_source: "machine" | "human_corrected";
  confidence: number;
  transcription_band: TranscriptionBand;
  band_label: string;
  band_description: string;
  needs_verification: boolean;
  line_count: number;
  word_count: number;
  provider: string;
  model_name: string;
  model_version: string;
  device: string;
  duration_ms: number;
  lines: LineResult[];
  preprocessing: PreprocessingReport | null;
  warnings: string[];
  created_at: string;
}

export interface Answer {
  id: string;
  question_id: string | null;
  booklet_ref: string | null;
  /** Pages of one uploaded document share this, which is what groups a booklet. */
  document_ref: string | null;
  /** Null on the per-question rows a marking run derives from a booklet. */
  page_number: number | null;
  source_filename: string | null;
  original_filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  status: AnswerStatus;
  image_url: string;
  created_at: string;
}

export interface AnswerDetail extends Answer {
  latest_ocr: OCRResult | null;
}

export interface AnswerWithOCR {
  answer: Answer;
  ocr: OCRResult;
}

export interface Accuracy {
  character_error_rate: number;
  word_error_rate: number;
  reference_characters: number;
  reference_words: number;
  hypothesis_characters: number;
  hypothesis_words: number;
  compared_against: string;
}

export interface ProviderInfo {
  name: string;
  model_name: string;
  model_version: string;
  device: string;
  is_ready: boolean;
  is_mock: boolean;
  detail: string;
}

export interface Band {
  band: string;
  min_confidence: number;
  label: string;
  description: string;
}

export interface Thresholds {
  transcription: Band[];
  evaluation: Band[];
}

export interface RoadmapPart {
  id: number;
  name: string;
  question: string;
  status: "available" | "planned";
  endpoints: string[];
}

/* ---- PDF documents ---- */

export interface PageResult {
  page_number: number;
  answer: Answer | null;
  ocr: OCRResult | null;
  error: string | null;
}

export interface DocumentTranscription {
  document_ref: string;
  filename: string | null;
  total_pages: number;
  pages_processed: number;
  pages: PageResult[];
  combined_text: string;
  overall_confidence: number;
  transcription_band: TranscriptionBand;
  band_label: string;
  total_lines: number;
  total_words: number;
  duration_ms: number;
  warnings: string[];
}

export interface PdfInspection {
  filename: string | null;
  total_pages: number;
  estimated_seconds: number;
  note: string;
}

/* ---- Part 2: questions and rubrics ---- */

export interface Criterion {
  id: string;
  position: number;
  description: string;
  max_marks: number;
  essential_concepts: string[];
  acceptable_alternatives: string[];
  common_mistakes: string[];
  allows_partial: boolean;
  load_bearing: boolean;
}

export interface Rubric {
  id: string;
  question_id: string;
  version: number;
  is_active: boolean;
  marking_scheme: string | null;
  scoring_rules: Record<string, unknown>;
  criteria: Criterion[];
  total_criterion_marks: number;
  created_at: string;
}

export interface Question {
  id: string;
  exam_id: string;
  number: string | null;
  text: string;
  topic: string | null;
  question_type: string;
  max_marks: number;
  answer_key: string | null;
  has_rubric: boolean;
  rubric: Rubric | null;
  created_at: string;
}

export interface Exam {
  id: string;
  title: string;
  subject: string;
  subject_code: string | null;
  term: string | null;
  question_count: number;
  total_marks: number;
  created_at: string;
}

export interface ExamDetail extends Exam {
  questions: Question[];
}

export interface RubricProblem {
  question: string;
  severity: "error" | "warning";
  message: string;
}

export interface RubricValidation {
  exam_id: string;
  is_valid: boolean;
  questions_checked: number;
  criteria_checked: number;
  total_marks: number;
  problems: RubricProblem[];
}

/* ---- Part 3: evaluation ---- */

export type ReviewBand =
  | "auto_accept"
  | "quick_review"
  | "mandatory_review"
  | "detailed_verification";

export type Verdict = "satisfied" | "partially_satisfied" | "not_satisfied";

export interface EvaluationCriterion {
  id: string;
  position: number;
  description: string;
  awarded_marks: number;
  max_marks: number;
  verdict: Verdict;
  reason: string;
  evidence_quote: string | null;
  evidence_found: boolean;
}

export interface Evaluation {
  id: string;
  answer_id: string;
  question_id: string | null;
  question_number: string | null;
  rubric_id: string | null;
  rubric_version: number;
  ocr_result_id: string | null;
  score: number;
  max_score: number;
  percentage: number;
  confidence: number;
  review_band: ReviewBand;
  band_label: string;
  band_description: string;
  needs_review: boolean;
  overall_explanation: string;
  confidence_signals: {
    signals?: Record<string, number>;
    weights?: Record<string, number>;
    unmeasured?: string[];
    samples?: number;
    disputed_criteria?: number[];
    ungrounded_criteria?: number[];
    load_bearing_criteria?: number[];
    method?: string;
    note?: string;
  };
  criteria: EvaluationCriterion[];
  warnings: string[];
  provider: string;
  model_name: string;
  prompt_version: string;
  text_source: string;
  duration_ms: number;
  created_at: string;
}

export interface QuestionSegment {
  question_id: string;
  question_number: string | null;
  question_text: string;
  max_marks: number;
  text: string;
  page_numbers: number[];
  located_by: string;
  transcription_confidence: number;
  found: boolean;
}

export interface BookletSegmentation {
  document_ref: string;
  exam_id: string;
  segments: QuestionSegment[];
  unmatched_text: string;
  warnings: string[];
}

export interface BookletResult {
  document_ref: string;
  exam_id: string;
  exam_title: string;
  booklet_ref: string | null;
  total_score: number;
  total_max: number;
  percentage: number;
  overall_confidence: number;
  review_band: ReviewBand;
  band_label: string;
  questions_marked: number;
  questions_total: number;
  needs_review: string[];
  evaluations: Evaluation[];
  segmentation: BookletSegmentation | null;
  duration_ms: number;
  warnings: string[];
}

export interface EvaluatorInfo {
  name: string;
  model_name: string;
  model_version: string;
  prompt_version: string;
  is_ready: boolean;
  is_mock: boolean;
  detail: string;
}

export interface ConfidenceWeights {
  weights: Record<string, number>;
  method: string;
  floor: number;
  grounding_match_threshold: number;
  signals: Record<string, string>;
  note: string;
}

/* ---- Part 4: review and validation ---- */

export interface Review {
  id: string;
  answer_id: string;
  evaluation_id: string | null;
  reviewer_id: string | null;
  action: "accept" | "modify";
  final_score: number;
  ai_score_at_review: number | null;
  delta: number | null;
  comments: string | null;
  duration_ms: number;
  created_at: string;
}

export interface BandAgreement {
  band: string;
  label: string;
  evaluations: number;
  reviewed: number;
  accepted: number;
  modified: number;
  modification_rate: number | null;
  mean_absolute_delta: number | null;
}

export interface Analytics {
  answers_uploaded: number;
  answers_transcribed: number;
  evaluations: number;
  reviews: number;
  mean_transcription_confidence: number | null;
  mean_evaluation_confidence: number | null;
  reviewed_evaluations: number;
  exact_agreement: number | null;
  within_half_mark: number | null;
  mean_absolute_error: number | null;
  by_band: BandAgreement[];
  mean_review_seconds: number | null;
  note: string;
}
