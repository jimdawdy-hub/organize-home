# organize-home Categorization Rules

This file is loaded by the agent during Phase 5 (AI document review) to guide
consistent categorization decisions.

## Rule-Based Moves (Phase 3 — no AI needed)

| Extension(s) | Destination |
|---|---|
| Filenames containing `bank statement`, `invoice`, or `receipt` in `~/Downloads/` | `~/Financial/` |
| Filenames containing `DMR` in `~/Downloads/` | `~/HamRadio/` |
| Filenames containing `letter to`, `cover letter`, or `correspondence` in `~/Downloads/` | `~/Correspondence/` |
| Filenames containing `resume` or `CV` in `~/Downloads/` | `~/Career/` |
| Filenames containing `personal` in `~/Downloads/` and not otherwise classified | `~/Personal/` |
| Filenames that look like a case citation in `~/Downloads/` | `~/Legal Reference/` |
| Filenames containing `medical records`, `bills`, `deposition`, or `transcript` in `~/Downloads/` | `~/Medical Files/` |
| Filenames containing `motion`, `order`, `orders`, `ct order`, `court`, `judge`, `plaintiff`, `defendant`, or `response` in `~/Downloads/` | `~/Legal Filings/` |
| .zip .gz .bz2 .xz .7z .rar .tar | ~/Zip Archive/ |
| .eml .msg | ~/Emails/ |
| .epub .mobi .azw3 | ~/Books/ |
| Executable in Downloads/ | ~/Downloads/ExecFiles/ |
| .jpg .jpeg .png .gif .webp .heic (in home, Documents, Downloads) | ~/Pictures/ |

## AI Document Categorization (Phase 5)

When reviewing a document, assign it to the MOST SPECIFIC existing folder if one
fits well. If no existing folder fits, create a new descriptive first-level folder.

### Preferred Existing Folders (match before creating new)

- `~/Documents/` — generic documents with no better home
- `~/Practice Files/` — client matters, practice materials, and work documents
- `~/Financial/` — bank statements, tax records, invoices, financial reports
- `~/HamRadio/` — amateur radio, ARRL, frequencies, callsigns, equipment
- `~/Career/` — resumes, job applications, professional development
- `~/Genealogy/` — family history, ancestry, birth/death records
- `~/Travel/` — itineraries, bookings, travel documents
- `~/Legal Reference/` — case citations, reporter references, published opinions
- `~/Personal Records/` — medical, insurance, identification documents
- `~/Personal/` — miscellaneous personal items after review
- `~/Academic/` — coursework, research, educational materials
- `~/Books/` — ebooks (handled in Phase 3), also PDFs of books/manuals
- `~/Pictures/` — images (handled in Phase 3)

### Folder Naming Guidelines

- Match existing folder names exactly when close enough
  - e.g., "Practice Files" NOT "Practice" if the former already exists
- Create new folders for genuinely new categories:
  - `~/Family/` — personal family matters, household records
  - `~/Contracts/` — if many legal contracts outside law practice
  - `~/Medical/` — if separate from Personal Records makes sense
- Name folders by topic, not by file type
  - GOOD: `~/Legal Filings/`, `~/Tax Records/`
  - BAD: `~/PDFs/`, `~/WordDocs/`

### Confidence Scoring Guidelines

- **0.8–1.0** — First page clearly identifies the document type and subject
- **0.5–0.8** — Reasonable inference but some ambiguity (multiple plausible folders)
- **0.3–0.5** — Significant uncertainty; route to low-confidence queue
- **0.0–0.3** — Cannot determine; route to ~/Human Review/

### Special Cases

- Downloads filename routing wins before file-type routing:
  - matching is plain case-insensitive substring appearance anywhere in the filename
  - `bank statement`, `invoice`, or `receipt` → `~/Financial/`
  - `DMR` → `~/HamRadio/`
  - `letter to`, `cover letter`, or `correspondence` → `~/Correspondence/`
  - `resume` or `CV` → `~/Career/`
  - case citation format (`Smith v. Jones 2017 Ill. App.` etc.) → `~/Legal Reference/`
  - `medical records`, `bills`, `deposition`, `transcript` → `~/Medical Files/`
  - `motion`, `order`, `orders`, `ct order`, `court`, `judge`, `plaintiff`, `defendant`, `response` → `~/Legal Filings/`
- Legal filings with case numbers/court names → `~/Practice Files/` or `~/Legal Filings/`
- Bank statements → `~/Financial/`
- Password files, credentials → `~/Personal Records/` (flag to user)
- Code/scripts not in a project folder → `~/Coding Projects/` if exists
- Empty or near-empty documents → confidence 0.1, route to Human Review
