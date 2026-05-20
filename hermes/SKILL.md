---
name: organize-home
description: Organizes the user's home directory by backing it up, sorting files by type, using AI to categorize documents, renaming unnamed images, and generating a browsable HTML index. Use when the user says "organize my home", "clean up my files", or "sort my downloads".
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [files, organization, home, cleanup]
    category: files
    requires_toolsets: [terminal]
    fallback_for_toolsets: [vision]
    config:
      - key: organize_home.default_backup_path
        description: "Default backup destination path (e.g. /mnt/data)"
        default: ""
        prompt: "Where should home backups be stored by default? (leave blank to always ask)"
---

# organize-home

Organizes ~/home by backing up, sorting files into typed folders, and producing an HTML index.
Scripts live at `~/organize-home/scripts/`. State file: `~/.organize-home-state.json`.

## Vision capability
This skill uses `fallback_for_toolsets: [vision]` — if your model does not have vision
capability, image AI-description steps are automatically skipped and EXIF/date naming
is used instead. At runtime, also confirm with a self-test:
1. `python3 -c "from PIL import Image; img=Image.new('RGB',(1,1),(255,255,255)); img.save('/tmp/vision_test.png')"`
2. Attempt to describe `/tmp/vision_test.png`. If successful, record vision=true in state. Otherwise record vision=false.

## Config
If `organize_home.default_backup_path` is set in your config.yaml, pre-select it as the
recommended backup option in Phase 0 — but always confirm with the user before proceeding.

## Resume check
At the start of every run, check `~/.organize-home-state.json`. If it exists, read
`completed_phases` and skip those phases. Tell the user: "Resuming from phase N."

---

## Phase 0: Preflight

1. Verify: `tar`, `file`, `exiftool` are on PATH. Verify Python packages: `python3 -c "import pypdf, docx, PIL"`
2. Detect drives:
```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/organize-home')
from scripts.backup import detect_drives
import json; print(json.dumps(detect_drives(), indent=2))
"
```
3. If `organize_home.default_backup_path` is configured, show it as the recommended option. Always confirm with user. Warn that `/tmp` is cleared on reboot.
4. Run vision self-test. Record result in state.
5. Mark phase 0 complete.

## Phase 1: Backup

```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/organize-home')
from scripts.backup import create_backup
result = create_backup('$HOME', 'CONFIRMED_BACKUP_DIR')
print(result)
"
```
Record backup path in state. Abort if backup fails. Mark phase 1 complete.

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
- If `exif_date` present: rename using exif date
- If `exif_date` null AND vision=true: describe image and use a descriptive slug
- If `exif_date` null AND vision=false: use mtime date

All renames: `python3 $HOME/organize-home/scripts/rename_images.py --rename "<path>" "<stem>"`
Mark phase 4 complete.

## Phase 5: AI document review

Load `~/organize-home/references/rules.md` now for categorization guidance.

For each file in `/tmp/unrouted.json` with extension `.pdf .doc .docx .txt .md .odt .rtf`:
1. `python3 $HOME/organize-home/scripts/ai_review.py --extract "/path/to/file"` → get text
2. Review text, decide: `{"category":"...","folder":"...","confidence":0.0–1.0,"reason":"..."}`
3. `python3 $HOME/organize-home/scripts/ai_review.py --record "/path/to/file" '<json>'`
4. confidence > 0.5 → move file immediately; ≤ 0.5 → leave for clarification

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
