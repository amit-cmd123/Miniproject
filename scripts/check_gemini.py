"""Check that Gemini handwriting recognition works with your key.

Run after adding EVALNOVA_GEMINI_API_KEY to .env, and before a demo:

    .venv\\Scripts\\python scripts\\check_gemini.py --list    # which models work
    .venv\\Scripts\\python scripts\\check_gemini.py           # a sample sheet
    .venv\\Scripts\\python scripts\\check_gemini.py path\\to\\page.png

Reads one page through the same pipeline the application uses, then prints
the transcription, the per-line confidence, how that confidence was measured,
and how long it took. Sends the page to Google.

`--list` answers the question that actually goes wrong in practice. A key is
rarely bad; a model is frequently unavailable - returning 503 under load, or
404 to a free tier - and the failure reads like a broken key. This prints the
models the key can see, then calls each candidate to find which really answer.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def list_models() -> int:
    """Print the models this key can reach, and which ones respond."""
    from app.core.config import settings
    from app.providers.gemini_rest import (
        GeminiRequestError,
        first_text,
        generate,
        list_models as fetch_models,
    )

    if not settings.gemini_api_key:
        print("No key found. Add EVALNOVA_GEMINI_API_KEY to .env.")
        return 1

    try:
        models = fetch_models(api_key=settings.gemini_api_key)
    except GeminiRequestError as exc:
        print(f"Could not list models: {exc}")
        return 1

    names = [m["name"].removeprefix("models/") for m in models]
    print(f"{len(names)} models support generateContent with this key.\n")

    # Listing a model proves nothing about being able to use it, so the
    # configured chain is actually called.
    candidates = list(
        dict.fromkeys(settings.gemini_model_chain + settings.evaluation_model_chain)
    )
    print("Calling the models this project is configured to use:\n")
    working: list[str] = []

    for model in candidates:
        if model not in names:
            print(f"  {model:<28} not available to this key")
            continue
        started = time.perf_counter()
        try:
            reply = generate(
                api_key=settings.gemini_api_key,
                model=model,
                body={
                    "contents": [
                        {"role": "user", "parts": [{"text": "Reply with: ready"}]}
                    ],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 512},
                },
                timeout_seconds=30.0,
            )
            first_text(reply)
            print(f"  {model:<28} OK   {time.perf_counter() - started:.1f}s")
            working.append(model)
        except GeminiRequestError as exc:
            print(f"  {model:<28} FAIL {str(exc)[:88]}")

    if working:
        print(f"\nUsable now: {', '.join(working)}")
        print(f"Set EVALNOVA_GEMINI_MODEL={working[0]} if the current one is failing.")
    else:
        print(
            "\nNone of the configured models answered. Pick others from the list "
            "above and set EVALNOVA_GEMINI_MODEL / EVALNOVA_GEMINI_FALLBACK_MODELS."
        )
        print("\nAll available model names:")
        for name in names:
            print(f"  {name}")
    return 0 if working else 1


def main() -> int:
    if "--list" in sys.argv:
        return list_models()
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
