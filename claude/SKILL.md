---
name: organize-home
description: Organizes the user's home directory by backing it up, sorting files by type, using AI to categorize documents, renaming unnamed images, and generating a browsable HTML index. Use when the user says "organize my home", "clean up my files", "sort my downloads", or similar.
version: 1.0.0
---

# organize-home

Organizes ~/home by backing up, sorting files into typed folders, and producing an HTML index.
Scripts live at `~/organize-home/scripts/`. State file: `~/.organize-home-state.json`.

## Required binaries
Before starting, verify these are installed: `tar`, `file`, `exiftool`.
If any are missing, print install instructions and stop:
- exiftool: `sudo pacman -S perl-image-exiftool` (Arch) or `sudo apt install libimage-exiftool-perl`
- tar, file: pre-installed on Linux

Verify Python packages:
```bash
python3 -c "import pypdf, docx, PIL"
```
If missing: `pip install pypdf python-docx Pillow` (or `sudo pacman -S python-pypdf python-pillow`)

## Vision capability test
Before Phase 4, test whether you can describe images:
1. `python3 -c "from PIL import Image; img=Image.new('RGB',(1,1),(255,255,255)); img.save('/tmp/vision_test.png')"`
2. Attempt to describe `/tmp/vision_test.png`
3. If you can describe it (e.g. "a white pixel"), set vision=true in state via:
   `python3 -c "import sys; sys.path.insert(0,'$HOME/organize-home'); from scripts.state import StateManager; sm=StateManager(); sm.set_vision(True)"`
4. Otherwise set vision=false.

## Resume check
At the start of every run, check `~/.organize-home-state.json`. If it exists, read
`completed_phases` and skip those phases. Tell the user: "Resuming from phase N."

---

## Phase 0: Preflight

1. Run dep checks above.
2. Detect drives:
```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/organize-home')
from scripts.backup import detect_drives
import json; print(json.dumps(detect_drives(), indent=2))
"
```
3. Present drive options to user (ranked by free space). Include `/tmp/home-backup-$(date +%Y%m%d)` as last-resort option with warning: "This will be deleted on reboot."
4. Ask user to confirm backup destination before proceeding.
5. Run vision test and record result in state.
6. Mark phase 0 complete:
```bash
python3 -c "import sys; sys.path.insert(0,'$HOME/organize-home'); from scripts.state import StateManager; sm=StateManager(); sm.mark_phase_complete(0)"
```

## Phase 1: Backup

```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/organize-home')
from scripts.backup import create_backup
result = create_backup('$HOME', 'CONFIRMED_BACKUP_DIR')
print(result)
"
```
Replace CONFIRMED_BACKUP_DIR with the path the user confirmed. Record backup path in state. If it fails, abort the entire run and tell the user. Mark phase 1 complete.

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
This prints a JSON list of `[{path, exif_date}, ...]`.

For each image in the list:
- If `exif_date` is not null: `python3 $HOME/organize-home/scripts/rename_images.py --rename "<path>" "<exif_date>"`
- If `exif_date` is null AND vision=true: view the image, create a descriptive slug (max 6 words, lowercase hyphenated), then: `python3 $HOME/organize-home/scripts/rename_images.py --rename "<path>" "<your-slug>"`
- If `exif_date` is null AND vision=false: get mtime: `python3 -c "from scripts.rename_images import get_mtime_date; print(get_mtime_date('<path>'))"`, then rename with mtime date.

Mark phase 4 complete.

## Phase 5: AI document review

Load `~/organize-home/references/rules.md` now for categorization guidance.

For each file in `/tmp/unrouted.json` with extension in `.pdf .doc .docx .txt .md .odt .rtf`:

```bash
python3 $HOME/organize-home/scripts/ai_review.py --extract "/path/to/file"
```

Review the extracted text. Decide category and confidence. Then record:
```bash
python3 $HOME/organize-home/scripts/ai_review.py --record "/path/to/file" \
  '{"category":"Legal","folder":"/home/user/Legal","confidence":0.85,"reason":"Contract language"}'
```

If confidence > 0.5: move the file now with `mv` or `shutil.move`.
If confidence ≤ 0.5: do NOT move the file. It is queued.

Mark phase 5 complete.

## Phase 6: HTML report

```bash
python3 $HOME/organize-home/scripts/html_report.py \
  --state $HOME/.organize-home-state.json \
  --home $HOME \
  --output $HOME/home-index.html
```
Mark phase 6 complete.

## Phase 7: Clarification (if needed)

Check state for `low_confidence` entries. If non-empty, tell the user:

> "I've organized everything I'm confident about. Open file://$HOME/home-index.html — the amber section lists [N] files I'm uncertain about, with my proposed destinations. Tell me which moves to make, correct any proposals, or say 'move all proposed' to accept them all."

Wait for user response. Apply moves as directed. Update state.

## Phase 8: Final report

Re-run the Phase 6 command. Then clean up:
```bash
python3 -c "import sys; sys.path.insert(0,'$HOME/organize-home'); from scripts.state import StateManager; StateManager().clear()"
```
Tell the user: "Done. Your home directory has been organized. Open file://$HOME/home-index.html to browse the result."
