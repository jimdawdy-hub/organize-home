"""Document first-page text extractor and AI review result recorder.

CLI modes:
  --extract <path>               Print first-page text to stdout (for agent to review)
  --record <path> <json_result>  Record agent's categorization result into state file
"""
import json
import sys
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".csv", ".log"}
REVIEWABLE_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".rtf"} | TEXT_EXTENSIONS
MAX_TEXT_CHARS = 3000


def extract_first_page(path: str) -> str | None:
    """Extract first-page text from a document. Returns None for unsupported types."""
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(path)
    if ext in (".docx", ".doc"):
        return _extract_docx(path)
    if ext in TEXT_EXTENSIONS:
        return _extract_text(path)
    if ext in (".odt", ".rtf"):
        return _extract_raw_fallback(path)
    return None


def _extract_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        if not reader.pages:
            return ""
        return reader.pages[0].extract_text() or ""
    except Exception:
        return ""


def _extract_docx(path: str) -> str:
    try:
        from docx import Document
        doc = Document(path)
        lines = []
        for para in doc.paragraphs[:40]:
            lines.append(para.text)
            if sum(len(l) for l in lines) > MAX_TEXT_CHARS:
                break
        return "\n".join(lines)
    except Exception:
        return ""


def _extract_text(path: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return text[:MAX_TEXT_CHARS]
    except Exception:
        return ""


def _extract_raw_fallback(path: str) -> str:
    try:
        raw = Path(path).read_bytes()
        return raw[:MAX_TEXT_CHARS].decode("utf-8", errors="replace")
    except Exception:
        return ""


def record_result(path: str, result: dict, state) -> None:
    """Record AI categorization result into state.

    High confidence (>0.5): logged as pending move (agent will move the file).
    Low confidence (<=0.5): added to low_confidence queue.
    """
    confidence = result.get("confidence", 0)
    if confidence > 0.5:
        state.add_move(path, result["folder"], phase=5, rule=f"ai:{result['category']}")
    else:
        state.add_low_confidence(path, result.get("folder", ""), confidence, result.get("reason", ""))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ai_review.py --extract <path> | --record <path> <json>")
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "--extract":
        text = extract_first_page(sys.argv[2])
        if text is None:
            print(json.dumps({"error": "unsupported file type"}))
        else:
            print(json.dumps({"text": text}))
    elif mode == "--record":
        from scripts.state import StateManager
        result = json.loads(sys.argv[3])
        sm = StateManager()
        record_result(sys.argv[2], result, sm)
        print(json.dumps({"ok": True}))
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
