# organize-home

A multi-platform AI skill that organizes your Linux home directory: backs it up, sorts files into typed folders, uses AI to categorize documents, renames unnamed images, and generates a browsable HTML index.

> **Safety:** Hidden files and folders (`.ssh`, `.gnupg`, `.config`, dotfiles, etc.) are never touched. All AI-proposed destinations are validated against a safety blocklist. See [SECURITY.md](SECURITY.md) for the threat model and full list of safeguards.

## What it does

| Phase | Action |
|-------|--------|
| 0 | Preflight: checks dependencies, asks where to back up |
| 1 | Creates a timestamped tar archive of your home directory |
| 2 | Indexes files in `~` and first-level subdirectories (not recursive) |
| 3 | Moves archives, emails, ebooks, executables, and images automatically |
| 4 | Renames non-descriptive images using EXIF date → AI description → file date |
| 5 | AI reads the first page of each remaining document and routes it with a confidence score |
| 6 | Generates `~/home-index.html` — a browsable map of your home directory |
| 7 | Pauses if any files scored below 50% confidence — shows them highlighted in the HTML report |
| 8 | Final report + cleanup |

Runs are **resumable** — progress is saved to `~/.organize-home-state.json` and any interrupted run picks up where it left off.

If you want to resume explicitly after a completed backup, use:

```bash
python3 ~/organize-home/scripts/resume_workflow.py --home "$HOME"
```

If the state file was lost but the backup archive exists, rebuild the phase-1
state first:

```bash
python3 ~/organize-home/scripts/resume_workflow.py --home "$HOME" \
  --bootstrap-backup /mnt/data/home-backup-2026-05-20.tar.gz
```

To search common mount paths for the latest `home-backup-*.tar.gz`, omit the
archive path:

```bash
python3 ~/organize-home/scripts/resume_workflow.py --home "$HOME" --bootstrap-backup
```

## Requirements

### System binaries
```bash
# Arch Linux
sudo pacman -S perl-image-exiftool python-pypdf python-pillow pigz

# Debian/Ubuntu
sudo apt install libimage-exiftool-perl python3-pypdf python3-pil pigz

# tar and file are pre-installed on all Linux systems
```

`pigz` is optional but strongly recommended — when installed, the backup phase uses all CPU cores for compression (often 4–8× faster on modern machines). Without pigz, the backup falls back to single-threaded gzip.

### Python packages
```bash
pip install python-docx
# pypdf and Pillow via system packages above, or:
pip install pypdf Pillow
```

## Installation

Clone this repo to `~/organize-home/` — the SKILL.md files reference scripts at that path.

```bash
git clone https://github.com/your-org/organize-home.git ~/organize-home
```

> **If you clone to a different location**, edit the `sys.path.insert(0, ...)` lines in the SKILL.md file for your platform to point to your actual path.

### Claude Code

```bash
mkdir -p ~/.claude/plugins/local/organize-home
cp ~/organize-home/claude/SKILL.md ~/.claude/plugins/local/organize-home/SKILL.md
```

Restart Claude Code. Invoke with: *"organize my home directory"*

### OpenClaw

```bash
# Replace with your OpenClaw plugin directory
cp ~/organize-home/openclaw/SKILL.md <your-openclaw-plugin-dir>/organize-home/SKILL.md
```

Restart OpenClaw or run the skill reload command.

### Hermes

```bash
mkdir -p ~/.hermes/skills/files/organize-home
cp ~/organize-home/hermes/SKILL.md ~/.hermes/skills/files/organize-home/SKILL.md
```

Optionally set a default backup path in `~/.hermes/config.yaml`:
```yaml
organize_home:
  default_backup_path: /mnt/your-backup-drive
```

## File structure

```
~/organize-home/
├── scripts/            # Shared Python scripts (all platforms)
│   ├── state.py        # Resumable run state
│   ├── backup.py       # Drive detection + tar archive
│   ├── index_files.py  # Two-level directory walker
│   ├── categorize.py   # Rule-based file routing
│   ├── rename_images.py # EXIF/AI/date image rename chain
│   ├── ai_review.py    # Document text extraction + result recording
│   └── html_report.py  # HTML index generator
├── references/
│   └── rules.md        # Categorization rules (loaded by agent on demand)
├── claude/SKILL.md     # Claude Code platform skill
├── openclaw/SKILL.md   # OpenClaw platform skill
└── hermes/SKILL.md     # Hermes platform skill
```

## Categorization rules

Files are sorted in this order (first match wins):

| File type | Destination |
|-----------|-------------|
| Filenames containing `bank statement`, `invoice`, or `receipt` in `~/Downloads/` | `~/Financial/` |
| Filenames containing `DMR` in `~/Downloads/` | `~/HamRadio/` |
| Filenames containing `letter to`, `cover letter`, or `correspondence` in `~/Downloads/` | `~/Correspondence/` |
| Filenames containing `resume` or `CV` in `~/Downloads/` | `~/Career/` |
| Filenames containing `personal` in `~/Downloads/` and not otherwise classified | `~/Personal/` |
| Filenames that look like a case citation in `~/Downloads/` | `~/Legal Reference/` |
| Filenames containing `medical records`, `bills`, `deposition`, or `transcript` in `~/Downloads/` | `~/Medical Files/` |
| Filenames containing `motion`, `order`, `orders`, `ct order`, `court`, `judge`, `plaintiff`, `defendant`, or `response` in `~/Downloads/` | `~/Legal Filings/` |
| `.zip .gz .bz2 .xz .7z .rar .tar` | `~/Zip Archive/` |
| `.eml .msg` | `~/Emails/` |
| `.epub .mobi .azw3` | `~/Books/` |
| Executables in `~/Downloads/` | `~/Downloads/ExecFiles/` |
| Images in `~`, `~/Downloads/`, `~/Documents/` | `~/Pictures/` |
| PDFs, Word docs, text files | AI-reviewed, routed by content |

Downloads filename routing is intentionally case-insensitive and uses simple substring matching: if the rule text appears anywhere in the filename, it counts. This wins before the generic file-type rules above.
Personal items are handled in the AI review phase as a fallback to `~/Personal/` when nothing more specific matches.
`medical records`, `bills`, `deposition`, and `transcript` in `~/Downloads/` route to `~/Medical Files/` before broader legal rules, including embedded forms like `dmr3.csv`.

The AI creates new first-level folders as needed (e.g., `~/Family/`, `~/Financial/`). Files it can't categorize with >50% confidence are highlighted in the HTML report for your review.

## Image renaming

Images with non-descriptive names (all digits, camera defaults like `IMG_1234`, fewer than 6 characters) are renamed using:

1. EXIF `DateTimeOriginal` → `2024-03-15_001.jpg`
2. AI description (if vision-capable model) → `red-barn-winter-snowfall.jpg`
3. File modification date → `2024-03-15_001.jpg`

## Recovering from an interrupted run

If you `Ctrl-C` mid-phase, the state file at `~/.organize-home-state.json` reflects partial progress. You have two options:

1. **Resume**: just invoke the skill again — completed phases are skipped automatically.
2. **Restore from backup**: extract `~/.../home-backup-YYYY-MM-DD.tar.gz` to recover the original layout, then delete `~/.organize-home-state.json` to start fresh.

If `~/home-index.html` was generated, it lists every move that was recorded.

## Running the tests

```bash
cd ~/organize-home
pip install pytest pypdf python-docx Pillow
python -m pytest
```

97 tests across all scripts, including security/edge-case tests for XSS, command injection, AI prompt injection, symlink escape, dotfile handling, TOCTOU, cross-filesystem moves, state corruption, and confidence clamping.

## Security

See [SECURITY.md](SECURITY.md) for the full threat model and list of safeguards. Highlights:

- Hidden files (`.ssh`, `.gnupg`, `.config`, etc.) are never indexed or moved
- AI-proposed destinations are validated — folders outside home or in dotfile dirs are rejected
- Filenames in the HTML report are HTML-escaped; copyable shell commands use `shlex.quote()`
- Backups refuse destinations inside home (no archive-included-in-itself loops)
- All subprocess calls have explicit timeouts
- State file is schema-validated on load — corrupted state raises an explicit error
