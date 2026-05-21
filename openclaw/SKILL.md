---
name: organize-home
description: Organizes the user's home directory by backing it up, sorting files by type, using AI to categorize documents, renaming unnamed images, and generating a browsable HTML index. Use when the user says "organize my home", "clean up my files", or "sort my downloads".
metadata:
  openclaw:
    os: ["linux"]
    requires:
      bins: [tar, file, exiftool, python3]
---

# organize-home

Organizes ~/home by backing up, sorting files into typed folders, and producing an HTML index.
Scripts live at `~/organize-home/scripts/`. State file: `~/.organize-home-state.json`.

## Required Python packages
Verify: `python3 -c "import pypdf, docx, PIL"`. If missing:
`pip install pypdf python-docx Pillow` (or `sudo pacman -S python-pypdf python-pillow`)

## Vision capability self-test
Before Phase 4, test whether you have image description capability:
1. `python3 -c "from PIL import Image; img=Image.new('RGB',(1,1),(255,255,255)); img.save('/tmp/vision_test.png')"`
2. Attempt to describe the image at `/tmp/vision_test.png`
3. If you receive a meaningful description (e.g. "a single white pixel"), you have vision capability. Record vision=true in state. Otherwise record vision=false.
   All image AI-description steps depend on this flag — fall back to EXIF/date if false.

## Resume check
At the start of every run, check `~/.organize-home-state.json`. If it exists, read
`completed_phases` and skip those phases. Tell the user: "Resuming from phase N."

---

## Phase 0: Preflight

1. Verify binaries (tar, file, exiftool) and Python packages.
2. Detect drives:
```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/organize-home')
from scripts.backup import detect_drives
import json; print(json.dumps(detect_drives(), indent=2))
"
```
3. Present options ranked by free space. Include `/tmp/home-backup-$(date +%Y%m%d)` as last resort with warning it is deleted on reboot.
4. Ask user to confirm backup destination before proceeding.
5. Run vision self-test and record result in state.
6. Mark phase 0 complete.

## Phase 1: Backup

```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/organize-home')
from scripts.backup import create_backup
result = create_backup('$HOME', 'CONFIRMED_BACKUP_DIR')
print(result)
"
```
Abort entire run if backup fails. Record backup path in state. Mark phase 1 complete.

## Phase 2: Index

```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/organize-home')
from scripts.index_files import build_index, save_index
entries = build_index('$HOME')
save_index(entries, '$HOME/.organize-home-index.json')
print(f'Indexed {len(entries)} files')
"
```
Mark phase 2 complete.

## Phase 3: Rule-based moves

```bash
python3 -c "
import sys, json; sys.path.insert(0,'$HOME/organize-home')
from scripts.index_files import load_index
from scripts.categorize import apply_moves
from scripts.state import StateManager
sm = StateManager()
entries = load_index('$HOME/.organize-home-index.json')
unrouted = apply_moves(entries, '$HOME', sm)
print(f'Moved {len(entries)-len(unrouted)} files. {len(unrouted)} need AI review.')
with open('/tmp/unrouted.json','w') as f: json.dump(unrouted, f)
"
```
Mark phase 3 complete.

## Phase 4: Image rename

```bash
python3 $HOME/organize-home/scripts/rename_images.py --scan $HOME/Pictures
```
For each result:
- If `exif_date` present: `python3 $HOME/organize-home/scripts/rename_images.py --rename "<path>" "<exif_date>"`
- If `exif_date` null AND vision=true: describe the image, then `--rename "<path>" "<your-slug>"`
- If `exif_date` null AND vision=false: use mtime date, then `--rename`

Mark phase 4 complete.

## Phase 5: AI document review

Load `~/organize-home/references/rules.md` now for categorization guidance.

For each file in `/tmp/unrouted.json` with extension `.pdf .doc .docx .txt .md .odt .rtf`:
1. `python3 $HOME/organize-home/scripts/ai_review.py --extract "/path/to/file"` → get text
2. Review text, decide: `{"category":"...","folder":"...","confidence":0.0–1.0,"reason":"..."}`
3. `python3 $HOME/organize-home/scripts/ai_review.py --record "/path/to/file" '<json>' --home "$HOME"` — `--home` is required so the script can reject AI-proposed unsafe folders (outside home, dotfile dirs)
4. confidence > 0.5 AND folder is safe → move file now; ≤ 0.5 OR unsafe folder → leave for clarification

Mark phase 5 complete.

## Phase 6: HTML report

```bash
python3 $HOME/organize-home/scripts/html_report.py \
  --state $HOME/.organize-home-state.json \
  --home $HOME \
  --output $HOME/home-index.html
```
Mark phase 6 complete.

## Phase 7: Clarification

If `low_confidence` is non-empty in state:
> "Open file://$HOME/home-index.html — the amber section lists [N] uncertain files. Tell me which moves to make, correct proposals, or say 'move all proposed'."

Apply user instructions. Update state.

## Phase 8: Final report

Re-run Phase 6. Clear state. Tell user: "Done. Browse your organized home at file://$HOME/home-index.html"
