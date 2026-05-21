# Security Considerations

`organize-home` moves user files autonomously, executes subprocess commands,
parses untrusted document content, and generates an HTML report that the user
opens in a browser. These notes describe the threat model, the safeguards
implemented, and the residual risks you should understand before using it.

## Threat model

| Source of input | Why we treat it as untrusted |
|---|---|
| Filenames in `~` and subdirs | Can contain HTML, shell metacharacters, or Unicode tricks |
| Document content (PDF / DOCX / text) | Used as AI prompt input — vulnerable to prompt injection |
| AI-returned categorization JSON | Indirectly controlled by document content |
| `~/.organize-home-state.json` | Read on resume — must not be blindly trusted across runs |
| `/proc/mounts` | Trusted (root-owned), but parsed defensively |
| Mounted backup drives | Path validated; not parsed |

## Implemented safeguards

### Path safety (`scripts/safety.py`)
- `is_within_home()` — resolves symlinks before comparing, rejects paths whose
  resolved location is outside `$HOME`.
- `is_safe_destination()` — stricter: rejects ANY dot-prefixed path component
  (no writes into `.ssh`, `.gnupg`, `.config`, or any other hidden dir).
- A blocklist explicitly rejects `.ssh`, `.gnupg`, `.password-store`, `.aws`,
  `.docker`, `.kube`, browser profile dirs, and `.git`.

### File move safety (`scripts/categorize.py`)
- Source path is `resolve()`-d and rejected if it escapes home (defends against
  malicious symlinks like `~/Downloads/photo.jpg → /etc/passwd`).
- Destination is validated with `is_safe_destination` before any write.
- Collision-free name selection uses `O_CREAT | O_EXCL` to atomically reserve
  the destination name (closes the TOCTOU race in the previous `exists()` loop).
- Cross-filesystem moves use copy-then-verify-then-delete with size verification,
  so a partial copy never deletes the source.

### Backup safety (`scripts/backup.py`)
- Refuses backup destinations that resolve inside `$HOME`.
- `tar` invocation uses `--` separator to prevent path-as-option misparsing.
- `--one-file-system` blocks tar from following symlinks across mounts.
- Default excludes (`.cache`, `Trash`, `node_modules`, `.venv`, Steam library,
  browser caches, language toolchain caches) skip GB of churn.
- Timeout on tar (default 8 hours, configurable) prevents hung backups.

### AI prompt injection mitigations (`scripts/ai_review.py`)
- The AI-returned `folder` field is **always validated** against
  `is_safe_destination`. A document that tries to inject "categorize as folder
  /etc/cron.d" will fail validation and be queued for human review.
- `confidence` is clamped to `[0.0, 1.0]`; non-numeric values become 0.
- Missing `folder` field is handled gracefully (queued).

### HTML report safety (`scripts/html_report.py`)
- Every interpolated value goes through `html.escape()`. Filenames containing
  `<script>` or `<img onerror>` are rendered as literal text, not executed.
- The copyable "mv" shell command uses `shlex.quote()` on every argument so a
  filename with `'; rm -rf $HOME; '` becomes a quoted string, not a command
  injection. The data attribute embedding the string uses `json.dumps()` then
  `html.escape()` for double-defense.
- The directory tree skips dotfiles, so `~/.ssh/id_rsa` is never listed.

### Hidden file protection (`scripts/index_files.py`)
- The indexer skips any file or directory whose name starts with `.` at both
  depth 0 and depth 1. SSH keys, GPG keys, shell config, browser data, and
  application config are never touched.

### State file integrity (`scripts/state.py`)
- `load()` validates the JSON structure: top-level dict, expected types for
  every list field, supported schema version.
- A corrupted or hostile state file raises `StateCorruptError` rather than
  silently being acted upon.

### Subprocess hardening
- All `subprocess.run` calls have an explicit `timeout=`.
- `tar`, `exiftool`, and any other CLI argv uses a `--` separator before
  user-supplied paths.

## Residual risks (you should understand these)

### PDF / DOCX parser vulnerabilities
`pypdf` and `python-docx` have had historical CVEs (XXE, malformed structure
crashes). The risk is bounded because the documents are already on the user's
disk — they trust their own files. **Do not use this skill to organize a folder
of documents you downloaded from an attacker.** The AI categorization step
deliberately exposes attacker-controllable text to the model, which is also a
prompt-injection surface mitigated by folder validation but not eliminated.

### Concurrent runs
If two `organize-home` runs are started simultaneously (e.g., two terminals),
they may race on the state file. Atomic writes prevent corruption, but lost
updates are possible. **Do not run the skill twice at once.**

### `/tmp` backup destination
If the user picks `/tmp/home-backup-*/` as the backup destination, the backup
is lost on reboot. The skill warns about this; the user must confirm. On
multi-user systems, `/tmp` writes are also vulnerable to symlink races by other
local users.

### Vision capability self-test
The vision-capability test writes `/tmp/vision_test.png`. On multi-user
systems, this filename is predictable. A determined local attacker could
pre-create a symlink at that path. Risk: low (only affects the test result),
but consider using `tempfile.NamedTemporaryFile` for stronger isolation.

### Folder-creation by AI
The AI is allowed to create new first-level folders (e.g., `~/Family/`,
`~/Legal Filings/`). A clever prompt-injection could fragment the user's home
with bogus folders. These are validated as safe destinations (under home, no
dotdir), but the user should review the HTML report for unexpected folders.

### Recovery from interrupted runs
If you `Ctrl-C` mid-phase, the state file reflects partial progress. Resuming
will skip completed phases but the in-flight file may have been moved without
being recorded. **To recover from a failed run:** restore the tar backup, or
review `~/home-index.html` (if Phase 6 ran) and `~/.organize-home-state.json`
to reconcile manually before re-running.

## Reporting security issues

For non-public security issues, please email the maintainer directly rather
than opening a GitHub issue. For low-severity concerns or hardening
suggestions, open an issue.

## Out of scope

- Disk encryption — the backup tar is not encrypted; if your backup drive is
  unencrypted, anyone with physical access can read it. Use LUKS, FileVault,
  or VeraCrypt on the backup drive.
- Cloud sync — no cloud upload happens; if you put your backup on a synced
  folder (Dropbox, iCloud), that's on you.
- Multi-user systems — designed for single-user Linux desktops. Shared systems
  have their own threat model not addressed here.
