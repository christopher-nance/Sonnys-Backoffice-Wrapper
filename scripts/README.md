# Exploration Scripts

`explore.py` captures HTML fixtures and recorded form payloads from the live Backoffice test tenant. It is a developer tool, not a runtime dependency of the library.

## Safety

By default the script blocks all POST/PUT/DELETE/PATCH requests and records the intended payload as `tests/fixtures/payloads/blocked_*.json`. The login POST is always allowed (you can't explore an authenticated app without logging in).

To allow a specific write through for fixture capture, pass `--allow-write <tag>`:

```bash
SONNYS_BOT_PASSWORD='...' python scripts/explore.py \
    --subdomain washu \
    --username SonnysWrapperTestAccount \
    --allow-write employee_insert
```

Only use `--allow-write` for actions that have been explicitly approved by the user for submission.

## Outputs

- `tests/fixtures/html/<page_name>.html` — raw HTML snapshots
- `tests/fixtures/payloads/allowed_<tag>.json` — recorded payloads for allowed writes
- `tests/fixtures/payloads/blocked_<tag>_<nn>.json` — recorded payloads for blocked writes (the fixtures Phase 2-8 actually consume — they capture the real form shape without committing state)
- `tests/fixtures/exploration_notes.md` — human-readable notes, gotchas, URL patterns (written by hand after inspection)

## Environment

- `SONNYS_BOT_PASSWORD` — required. Credentials for the test bot user.
- Requires `playwright` installed (`.venv/Scripts/python.exe -m pip install playwright`) and the Chromium browser fetched (`playwright install chromium`).
