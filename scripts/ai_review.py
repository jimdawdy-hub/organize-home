"""Document first-page text extractor and AI review result recorder.

CLI modes:
  --extract <path>
      Print first-page text to stdout (for agent to review)
  --record <path> <json_result> --home <home_dir> [--state <state_path>]
      Record agent's categorization result into state file. The folder named in
      <json_result> is validated to be a safe destination under <home_dir>; if it
      is not, the file is queued for human review instead of being marked for move.

Safety:
  - AI-returned `folder` field is validated with safety.is_safe_destination;
    folders outside home or with any dot-prefixed component are rejected and the
    record is forced into the low_confidence queue.
  - confidence is clamped to [0.0, 1.0] and non-numeric values are treated as 0.
"""
import json
import sys
from pathlib import Path

try:
    from scripts.safety import is_safe_destination
except ImportError:
    from safety import is_safe_destination

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


def _clamp_confidence(value) -> float:
    """Coerce `value` into [0.0, 1.0]. Non-numeric values become 0.0."""
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    if c != c:  # NaN
        return 0.0
    return max(0.0, min(1.0, c))


def record_result(path: str, result: dict, state, home_dir: str = None) -> None:
    """Record AI categorization result into state.

    Args:
        home_dir: If provided, the folder named in `result` is validated with
            is_safe_destination. Folders that fail validation force the record
            into the low_confidence queue regardless of stated confidence.

    Routing:
        confidence > 0.5 AND folder is safe → state.add_move (queued for actual move)
        confidence ≤ 0.5 OR folder is unsafe/missing → state.add_low_confidence
    """
    confidence = _clamp_confidence(result.get("confidence", 0))
    folder = result.get("folder") or ""
    category = result.get("category", "")
    reason = result.get("reason", "")

    folder_safe = False
    if folder and home_dir:
        folder_safe = is_safe_destination(folder, home_dir)
    elif folder and not home_dir:
        # No home_dir to validate against — accept legacy behavior but flag it
        folder_safe = True

    if not folder:
        state.add_low_confidence(path, "", confidence,
                                 f"AI result missing 'folder' field; reason: {reason}")
        return

    if not folder_safe:
        state.add_low_confidence(
            path, folder, confidence,
            f"AI proposed unsafe destination {folder!r}; reason: {reason}"
        )
        return

    if confidence > 0.5:
        state.add_move(path, folder, phase=5, rule=f"ai:{category}")
    else:
        state.add_low_confidence(path, folder, confidence, reason)


def _load_state_manager(state_path: str | None):
    """Import StateManager with fallback for script vs. module invocation."""
    try:
        from scripts.state import StateManager
    except ImportError:
        from state import StateManager
    return StateManager(state_path) if state_path else StateManager()


if __name__ == "__main__":
    import argparse

    if len(sys.argv) >= 2 and sys.argv[1] == "--extract":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "missing path argument"}))
            sys.exit(1)
        text = extract_first_page(sys.argv[2])
        if text is None:
            print(json.dumps({"error": "unsupported file type"}))
        else:
            print(json.dumps({"text": text}))
        sys.exit(0)

    if len(sys.argv) >= 2 and sys.argv[1] == "--record":
        parser = argparse.ArgumentParser()
        parser.add_argument("--record", required=True, help="path of file being categorized")
        parser.add_argument("json_result", help="JSON-encoded categorization result")
        parser.add_argument("--home", required=True, help="home directory for safety validation")
        parser.add_argument("--state", default=None, help="state file path (default: ~/.organize-home-state.json)")
        args = parser.parse_args()
        result = json.loads(args.json_result)
        sm = _load_state_manager(args.state)
        record_result(args.record, result, sm, home_dir=args.home)
        print(json.dumps({"ok": True}))
        sys.exit(0)

    print("Usage:")
    print("  ai_review.py --extract <path>")
    print("  ai_review.py --record <path> <json> --home <home_dir> [--state <state_path>]")
    sys.exit(1)
