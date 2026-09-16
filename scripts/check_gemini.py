"""Check that Gemini handwriting recognition works with your key.

Run after adding EVALNOVA_GEMINI_API_KEY to .env, and before a demo:

    .venv\\Scripts\\python scripts\\check_gemini.py                   # a sample sheet
    .venv\\Scripts\\python scripts\\check_gemini.py path\\to\\page.png

Reads one page through the same pipeline the application uses, then prints
the transcription, the per-line confidence, how that confidence was measured,
and how long it took. Sends the page to Google.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    from app.core.config import settings
    from app.providers.ocr.gemini_provider import GeminiError, GeminiOCRProvider
    from app.services.preprocessing import crop_line, load_image, preprocess

    if not settings.gemini_api_key:
        print("No key found. Add this line to .env at the repository root:\n")
        print("    EVALNOVA_GEMINI_API_KEY=your-key-here\n")
        print("Get a key at https://aistudio.google.com/apikey")
        return 1

    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/samples/sample_answer_normal.png"
    provider = GeminiOCRProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=settings.gemini_timeout_seconds,
        thinking_level=settings.gemini_thinking_level,
    )
    image = load_image(image_path)
    clean, boxes, _ = preprocess(image)

    print(f"Model: {settings.gemini_model}\nPage:  {image_path}\n")
    started = time.perf_counter()
    try:
        result = provider.recognise_page(image, [crop_line(clean, b) for b in boxes], boxes)
    except GeminiError as exc:
        print(f"FAILED: {exc}")
        return 1
    elapsed = time.perf_counter() - started

    for line in result.lines:
        print(f"  {line.confidence:6.1%}  {line.text}")
    for warning in result.warnings:
        print(f"  ! {warning}")
    print(f"\nConfidence method: {result.confidence_method}")
    print(f"Time: {elapsed:.1f}s")

    reference = image_path.with_suffix(".txt")
    if reference.exists():
        import jiwer

        normalise = jiwer.Compose([jiwer.ToLowerCase(), jiwer.RemovePunctuation(),
                                   jiwer.RemoveMultipleSpaces(), jiwer.Strip()])
        ref = normalise(reference.read_text(encoding="utf-8").replace("\n", " "))
        hyp = normalise(result.text.replace("\n", " "))
        print(f"Character error rate: {jiwer.cer(ref, hyp):.1%}   Word error rate: {jiwer.wer(ref, hyp):.1%}")
    print("\nOK - set EVALNOVA_OCR_PROVIDER=gemini in .env and restart the backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
