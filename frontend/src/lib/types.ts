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
