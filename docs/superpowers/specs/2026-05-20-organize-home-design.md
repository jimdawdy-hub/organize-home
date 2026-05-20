# Design Spec: organize-home Skill

**Date:** 2026-05-20  
**Status:** Approved  
**Platforms:** Claude Code, OpenClaw, Hermes  

---

## Overview

A multi-platform skill that organizes `/home/user` (and any user's home directory) by:
1. Creating a backup before touching anything
2. Indexing first-level subdirectory contents
3. Automatically moving files into typed categories
4. Using AI to review and route documents with a confidence-scored fallback
5. Producing a browsable HTML index as both a report and a clarification interface

The skill is resumable — progress is checkpointed to `~/.organize-home-state.json` and any interrupted run picks up where it left off.

---

## Repository Structure

```
~/organize-home/
├── scripts/                    # Shared Python scripts (identical across all platforms)
│   ├── state.py                # Read/write/clear ~/.organize-home-state.json
│   ├── backup.py               # Create timestamped tar archive at user-confirmed path
│   ├── index_files.py          # Walk home + first-level subdirs, output JSON map
│   ├── categorize.py           # Rule-based file sorting (no AI)
│   ├── rename_images.py        # EXIF → AI description → date fallback rename chain
│   ├── ai_review.py            # Read doc first page, return category + confidence
│   └── html_report.py          # Generate/update browsable HTML index
├── references/
│   └── rules.md                # Categorization rules (loaded by agent on demand)
├── claude/
│   └── SKILL.md                # Claude Code platform version
├── openclaw/
│   └── SKILL.md                # OpenClaw platform version
└── hermes/
    └── SKILL.md                # Hermes platform version
```

---

## Execution Phases

Phases are executed in order. Each phase writes its completion to the state file before the next begins. On resume, completed phases are skipped.

| # | Phase | Prompts User? | Notes |
|---|-------|--------------|-------|
| 0 | **Preflight** | Yes — backup location | Checks deps, detects drives, asks where to backup |
| 1 | **Backup** | No | `tar czf <confirmed-path>/home-backup-YYYY-MM-DD.tar.gz /home/user` |
| 2 | **Index** | No | Walks `/home/user` + first-level subdirs only (not recursive into subdirs) |
| 3 | **Easy moves** | No | Rule-based: zips, emails, executables, epubs, images |
| 4 | **Image rename** | No | Non-descriptive filenames renamed via EXIF → AI → date chain |
| 5 | **Doc review** | No | AI reads first page, scores confidence, moves if >0.5 |
| 6 | **HTML report** | No | Generates `/home/user/home-index.html` |
| 7 | **Clarification** | Yes — if low-confidence files exist | Pauses, directs user to amber section of HTML report |
| 8 | **Final report** | No | Updates HTML after user-directed moves |

---

## Phase 0: Preflight

1. Check required binaries: `tar`, `file`, `exiftool`. Check Python packages: `pypdf`, `python-docx`, `Pillow`. If anything is missing, print install instructions and abort.
2. Detect mounted drives and available space. Rank candidates (largest available space first).
3. Present options to user:
   - Any detected external drives (e.g., `/mnt/data`)
   - `/tmp/home-backup-YYYYMMDD/` with a warning: *"This will be deleted on reboot — use only as a last resort"*
   - Custom path (user types it)
4. Confirm selection before proceeding.
5. Vision capability test: agent attempts to describe a 1×1 white PNG. If it fails, sets `vision: false` in state file. All image jobs use EXIF/date naming for the rest of the run.

---

## Phase 1: Backup

```
tar czf <confirmed-path>/home-backup-2026-05-20.tar.gz /home/user
```

Logs archive path and size to state file. Aborts entire run if tar fails.

---

## Phase 2: Index

`index_files.py` walks exactly two levels:
- Files directly in `/home/user/` (depth 0)
- Files in each immediate subdirectory of `/home/user/` (depth 1), e.g., `/home/user/Downloads/`, `/home/user/Documents/`

Does **not** recurse into `/home/user/Downloads/OldProject/subfolder/`. Outputs `~/.organize-home-index.json`:

```json
{
  "scanned_at": "2026-05-20T10:30:00",
  "files": [
    {
      "path": "/home/user/Downloads/contract.pdf",
      "size": 45231,
      "ext": ".pdf",
      "mtime": "2025-11-03T09:12:00",
      "is_executable": false
    }
  ]
}
```

---

## Phase 3: Rule-Based Categorization

Applied in order. First matching rule wins.

| Condition | Destination | Created if missing? |
|-----------|-------------|-------------------|
| Extension in `.zip .gz .bz2 .xz .7z .rar .tar` | `/home/user/Zip Archive/` | Yes |
| Extension in `.eml .msg` | `/home/user/Emails/` | Yes |
| Extension in `.epub .mobi .azw3` | `/home/user/Books/` | Yes |
| Executable bit set AND file is in `Downloads/` | `/home/user/Downloads/ExecFiles/` | Yes |
| Extension in `.jpg .jpeg .png .gif .webp .heic` AND file is in `/home/user/`, `Documents/`, or `Downloads/` | `/home/user/Pictures/` | Yes (already exists) |

Files already in their correct destination folder are skipped. Every move is logged to the state file.

---

## Phase 4: Image Rename

Applied to images moved to `Pictures/` in Phase 3 and any images already in `Pictures/` prior to the run.

**Trigger condition:** Filename is considered non-descriptive if it matches any of:
- All digits (e.g., `1000037861.jpg`)
- Fewer than 6 meaningful characters before the extension
- Camera default patterns: `IMG_XXXX`, `DSC_XXXX`, `DCIM_XXXX`, `PICT_XXXX`, `photo_XXXX`

**Rename chain (first success wins):**

1. `exiftool` EXIF DateTimeOriginal → `YYYY-MM-DD_NNN.ext` (NNN = sequence to avoid collisions)
2. If `vision: true` in state → agent describes image content → URL-safe slug, max 6 words (e.g., `red-barn-winter-snowfall.jpg`)
3. File modification date → `YYYY-MM-DD_NNN.ext`

---

## Phase 5: AI Document Review

Applied to all remaining unrouted files with extensions: `.pdf .doc .docx .txt .md .odt .rtf`

For each file, `ai_review.py` extracts the first page of text (`pypdf` for PDFs, `python-docx` for Word, plain read for text files) and passes it to the agent with the prompt:

> "Given this document excerpt, what category does it belong to? Choose or create a first-level folder name under /home/user/. Return JSON: `{category, folder, confidence, reason}`"

**Routing:**

| Confidence | Action |
|-----------|--------|
| > 0.5 | Move to `folder` immediately. Create folder if it doesn't exist. |
| ≤ 0.5 | Add to low-confidence queue. Do not move. |
| Error / unreadable | Move to `/home/user/Human Review/` |

The agent may create new first-level folders as needed (e.g., `/home/user/Family/`, `/home/user/Practice Files/`, `/home/user/HamRadio/`). Folder names are flexible — the agent should match existing folder names when close enough (e.g., if `Practice Files/` exists, don't create `Expat Law/`).

---

## Phase 6: HTML Report (Initial)

`html_report.py` generates `/home/user/home-index.html`:

**Sections:**
1. **Header** — run timestamp, summary stats (files found / moved / renamed / pending review)
2. **Run Log** — collapsible table: original path → new path, rule or AI reason
3. **Directory Tree** — clickable `file://` hyperlinks to every file, organized by folder
4. **Amber Section: Needs Your Input** — low-confidence files with:
   - Current location
   - Proposed destination folder
   - AI's confidence score and reasoning
   - Copyable terminal command to confirm the move
5. **Human Review Folder** — files the AI couldn't categorize; listed prominently

---

## Phase 7: Clarification Pause

If the low-confidence queue is non-empty, the agent pauses and tells the user:

> "I've organized everything I'm confident about. Open `file:///home/user/home-index.html` — the amber section lists [N] files I'm uncertain about, with my proposed destinations. Tell me which moves to make, correct any proposals, or say 'move all proposed' to accept them all."

The agent waits for user input and applies instructions file-by-file. Each resolved file is removed from the low-confidence queue in the state file.

---

## Phase 8: Final Report Update

`html_report.py` is re-run to produce an updated `home-index.html` reflecting all moves including post-clarification ones. State file is deleted (clean completion).

---

## Platform Differences

### Claude Code (`claude/SKILL.md`)
- Frontmatter: `name`, `description`, `version`
- Vision fallback: runtime self-test instruction in skill body
- Required bins: listed in skill body prose
- OS: Linux assumed in instructions

### OpenClaw (`openclaw/SKILL.md`)
- Frontmatter: adds `metadata.openclaw.os: ["linux"]` and `metadata.openclaw.requires.bins: [tar, file, exiftool]`
- Vision fallback: runtime self-test instruction in skill body (same as Claude)
- OS: explicitly filtered to Linux via metadata

### Hermes (`hermes/SKILL.md`)
- Frontmatter: adds `platforms: [linux]`, `metadata.hermes.category: files`, `requires_toolsets: [terminal]`
- Vision fallback: `fallback_for_toolsets: [vision]` in frontmatter AND runtime self-test instruction in skill body
- Config key: `organize_home.default_backup_path` — injected into context automatically from user's `config.yaml`

All three SKILL.md body text is ~90% identical. Platform-specific sections are clearly marked.

---

## Dependencies

| Tool | Type | Purpose | Install |
|------|------|---------|---------|
| `tar` | System binary | Backup | Pre-installed on Linux |
| `file` | System binary | Executable detection | Pre-installed on Linux |
| `exiftool` | System binary | Image EXIF date | `pacman -S perl-image-exiftool` |
| `pypdf` | Python package | Read PDF first page | `pip install pypdf` |
| `python-docx` | Python package | Read Word first page | `pip install python-docx` |
| `Pillow` | Python package | Fallback image date | `pip install Pillow` |

---

## State File Schema

`~/.organize-home-state.json`:

```json
{
  "version": 1,
  "started_at": "2026-05-20T10:00:00",
  "backup_path": "/mnt/data/home-backup-2026-05-20.tar.gz",
  "vision": true,
  "completed_phases": [0, 1, 2, 3],
  "moves": [
    {"from": "/home/user/Downloads/contract.zip", "to": "/home/user/Zip Archive/contract.zip", "phase": 3, "rule": "zip"}
  ],
  "low_confidence": [
    {"path": "/home/user/Downloads/mystery.pdf", "proposed": "/home/user/Human Review", "confidence": 0.3, "reason": "..."}
  ],
  "errors": []
}
```

---

## Out of Scope

- Files more than one level below `/home/user/` are not touched (e.g., `/home/user/Projects/myapp/src/` is untouched)
- No changes to file permissions
- No deduplication
- No cloud sync
- Windows or macOS support
