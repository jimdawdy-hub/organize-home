"""HTML report generator.

CLI: html_report.py --state <state_json_path> --home <home_dir> --output <html_path>

Security: all interpolated user/AI-controlled values are HTML-escaped. Shell commands
shown to the user for copy/paste are quoted with shlex.quote(). data-* attributes
embedding strings for JavaScript use json.dumps() (which produces valid HTML-attribute-
escaped JSON).
"""
import json
import shlex
import sys
from datetime import datetime
from html import escape as h
from pathlib import Path

CSS = """
body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 2rem; color: #333; }
h1 { color: #1a1a2e; } h2 { color: #16213e; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }
.stats { display: flex; gap: 2rem; background: #f8f9fa; padding: 1rem; border-radius: 8px; margin: 1rem 0; }
.stat { text-align: center; } .stat .num { font-size: 2rem; font-weight: bold; color: #0f3460; }
.stat .label { font-size: 0.85rem; color: #666; }
details summary { cursor: pointer; font-weight: bold; padding: 0.5rem; background: #f0f0f0; border-radius: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { background: #16213e; color: white; padding: 0.5rem; text-align: left; }
td { padding: 0.4rem 0.5rem; border-bottom: 1px solid #eee; }
tr:hover { background: #f8f9fa; }
.amber { background: #fff8e1; border: 2px solid #ffc107; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; }
.amber h2 { color: #856404; border-color: #ffc107; }
.confidence { font-weight: bold; color: #856404; }
.cmd { font-family: monospace; background: #f4f4f4; padding: 0.2rem 0.5rem; border-radius: 3px;
       border: 1px solid #ddd; cursor: pointer; }
.human-review { background: #fff3f3; border: 2px solid #dc3545; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; }
a { color: #0f3460; } a:hover { color: #e94560; }
"""


def _is_human_review(to_path: str) -> bool:
    """Return True if to_path is the dedicated Human Review folder.

    Uses exact parent-directory name match — not substring — so user folders
    named 'Human Review Notes' or 'Documents/Human Review' don't false-match.
    """
    if not to_path:
        return False
    p = Path(to_path)
    return p.parent.name == "Human Review" or p.name == "Human Review"


def generate_report(state: dict, home_dir: str, output_path: str) -> None:
    moves = state.get("moves", []) or []
    low_conf = state.get("low_confidence", []) or []
    errors = state.get("errors", []) or []
    backup_path = state.get("backup_path") or "unknown"
    started_at = state.get("started_at") or ""
    date_str = started_at[:10] if started_at else datetime.now().strftime("%Y-%m-%d")

    human_review_entries = [m for m in moves if _is_human_review(m.get("to", ""))]
    auto_moved = [m for m in moves if m not in human_review_entries]

    sections = []

    # Stats bar — counts are integers, no escaping needed; backup_path IS escaped
    sections.append(f"""
<div class="stats">
  <div class="stat"><div class="num">{len(moves)}</div><div class="label">files moved</div></div>
  <div class="stat"><div class="num">{len(low_conf)}</div><div class="label">needs review</div></div>
  <div class="stat"><div class="num">{len(human_review_entries)}</div><div class="label">human review</div></div>
  <div class="stat"><div class="num">{len(errors)}</div><div class="label">errors</div></div>
</div>
<p><strong>Backup:</strong> <code>{h(backup_path)}</code><br>
<strong>Run date:</strong> {h(date_str)}</p>
""")

    # Amber section — low confidence
    if low_conf:
        rows = ""
        for lc in low_conf:
            lc_path = str(lc.get("path", ""))
            lc_proposed = str(lc.get("proposed", ""))
            lc_reason = str(lc.get("reason", ""))
            lc_conf = float(lc.get("confidence", 0))
            conf_pct = f"{lc_conf*100:.0f}%"
            # shlex.quote handles single quotes safely (turns ' into '"'"')
            mv_cmd = f"mv {shlex.quote(lc_path)} {shlex.quote(lc_proposed)}"
            # json.dumps gives a valid JS string literal; h() then escapes for HTML attribute
            mv_cmd_attr = h(json.dumps(mv_cmd), quote=True)
            rows += f"""
<tr>
  <td><a href="file://{h(lc_path, quote=True)}">{h(Path(lc_path).name)}</a></td>
  <td><code>{h(lc_path)}</code></td>
  <td><code>{h(lc_proposed)}</code></td>
  <td class="confidence">{h(conf_pct)}</td>
  <td>{h(lc_reason)}</td>
  <td><span class="cmd" onclick="navigator.clipboard.writeText({mv_cmd_attr})">📋 copy</span></td>
</tr>"""
        sections.append(f"""
<div class="amber">
<h2>⚠️ Needs Your Input ({len(low_conf)} files)</h2>
<p>These files have a confidence score below 50%. Tell the agent which moves to make,
correct any proposals, or say <strong>"move all proposed"</strong> to accept them all.</p>
<table>
<tr><th>File</th><th>Current Location</th><th>Proposed Destination</th>
    <th>Confidence</th><th>Reason</th><th>Command</th></tr>
{rows}
</table>
</div>""")

    # Human Review section
    if human_review_entries:
        rows = "".join(
            f'<tr><td><a href="file://{h(m["from"], quote=True)}">{h(Path(m["from"]).name)}</a></td>'
            f'<td><code>{h(m["from"])}</code></td></tr>'
            for m in human_review_entries
        )
        sections.append(f"""
<div class="human-review">
<h2>🔍 Human Review ({len(human_review_entries)} files)</h2>
<p>The AI could not categorize these files. Please review them manually.</p>
<table><tr><th>File</th><th>Original Location</th></tr>{rows}</table>
</div>""")

    # Move log
    if auto_moved:
        rows = "".join(
            f'<tr><td><a href="file://{h(m["to"], quote=True)}">{h(Path(m["from"]).name)}</a></td>'
            f'<td><code>{h(m["from"])}</code></td>'
            f'<td><code>{h(m["to"])}</code></td>'
            f'<td>{h(m.get("rule", ""))}</td></tr>'
            for m in auto_moved
        )
        sections.append(f"""
<details open>
<summary>Run Log ({len(auto_moved)} moves)</summary>
<table>
<tr><th>File</th><th>From</th><th>To</th><th>Rule</th></tr>
{rows}
</table>
</details>""")

    # Directory tree
    sections.append(_build_dir_tree(home_dir))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Home Directory Index — {h(date_str)}</title>
<style>{CSS}</style>
</head>
<body>
<h1>Home Directory Index</h1>
{"".join(sections)}
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _build_dir_tree(home_dir: str) -> str:
    home = Path(home_dir)
    items = ["<h2>Directory Tree</h2><ul>"]
    try:
        for item in sorted(home.iterdir()):
            # Skip hidden files/folders — they aren't part of the organized layout
            if item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f'<li>📁 <strong>{h(item.name)}/</strong><ul>')
                try:
                    for child in sorted(item.iterdir()):
                        if child.is_file() and not child.name.startswith("."):
                            items.append(
                                f'<li><a href="file://{h(str(child), quote=True)}">📄 {h(child.name)}</a></li>'
                            )
                except PermissionError:
                    pass
                items.append("</ul></li>")
            elif item.is_file():
                items.append(f'<li><a href="file://{h(str(item), quote=True)}">📄 {h(item.name)}</a></li>')
    except PermissionError:
        pass
    items.append("</ul>")
    return "\n".join(items)


if __name__ == "__main__":
    import argparse
    from scripts.state import StateManager
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    sm = StateManager(args.state)
    generate_report(sm.load(), args.home, args.output)
    print(f"Report written to {args.output}")
