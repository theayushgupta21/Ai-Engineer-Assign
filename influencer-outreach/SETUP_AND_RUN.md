# Setup and Run from Scratch

This guide takes a fresh Windows checkout from Python setup to an offline test run and a staged pipeline run. The pipeline uses real public YouTube data only when you start discovery; tests use labeled fake fixtures and make no network requests.

## 1. Prerequisites

- Windows 10/11 and PowerShell
- Python 3.11 or newer
- A YouTube Data API v3 key for discovery and enrichment
- A Groq API key for personalization
- SMTP credentials only if you choose to test delivery to your own test inbox

Do not paste credentials into source files, this guide, `.env.example`, or chat. Credentials previously shared in this project should be revoked and replaced before use.

## 2. Create the environment

Open PowerShell in the project folder, then run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `py -3.11` is unavailable, install Python 3.11+ from python.org and repeat. You do not need to activate the virtual environment when using the explicit `.venv` commands above.

## 3. Add local credentials

First verify `.env.example` contains placeholders only. The current workspace copy has value-present sensitive entries, so sanitize it before copying or committing it. Create the ignored local environment file once:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Open `.env` in VS Code and replace the placeholders locally:

```dotenv
YOUTUBE_API_KEY=your_rotated_youtube_api_key
GROQ_API_KEY=your_groq_api_key
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_sender_account@gmail.com
SMTP_PASSWORD=your_rotated_app_password
TEST_INBOX=your_test_inbox@gmail.com
DRY_RUN=true
```

SMTP values are only needed for `send --live`. The live sender delivers to `TEST_INBOX`, never to influencer addresses. Check that `.env` is ignored by Git:

```powershell
git check-ignore .env
```

It should print `.env` (or its path). Keep `.env.example` as placeholders.

## 4. Set the brand and filters

Edit `config.yaml`:

- Replace `YOUR_BRAND` and `YOUR_PRODUCT`, and set a truthful `value_prop`.
- Adjust discovery keywords, region, language, and target count as needed.
- Review follower, engagement, activity, and niche thresholds.
- The checked-in model is `openai/gpt-oss-20b`; `openai/gpt-oss-120bt` is noted as the quality fallback. Choose a model available to your Groq account if either is unavailable.
- Review `personalization.max_tokens`, `temperature`, `max_retries`, and `delay_between_requests_seconds` before a large run.
- Leave `sending.dry_run: true` for the normal safe default.

The configured brand facts are passed into generated messages, so do not use claims the brand cannot support.

## 5. Run offline tests first

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

This validates utility functions and pipeline behavior with fake YouTube/LLM/SMTP dependencies. It does not require API credentials and does not send messages.

## 6. Run the pipeline by stage

Run each step in order so you can inspect the output before continuing:

```powershell
.\.venv\Scripts\python.exe main.py discover
.\.venv\Scripts\python.exe main.py enrich
.\.venv\Scripts\python.exe main.py filter
.\.venv\Scripts\python.exe main.py personalize
```

Before rerunning personalization after a failed run, delete the stale `data/messages.csv` so old drafts cannot mix with new results. In PowerShell, remove it manually with `Remove-Item data\messages.csv` (only if it exists). This file is not deleted automatically.

`discover` calls YouTube Data API v3 and writes `data/raw_channels.csv`. `enrich` writes `data/influencers.csv`. `filter` keeps every row, adds status/reasons, and creates `data/shortlist.csv`. `personalize` calls Groq and writes successful drafts to `data/messages.csv`. Failed individual rows are skipped; fatal key/account/model errors abort the stage. If all rows fail, it exits non-zero and does not write a new messages file.

The complete sequence is also available as:

```powershell
.\.venv\Scripts\python.exe main.py run-all
```

`run-all` does not automatically approve drafts. Review the generated CSV before sending.

## 7. Review and test sending

Open `data/messages.csv`. Check every subject, email, and DM. Set `approved` to `true` only for drafts you approve, then save and close the CSV editor so changes are written.

First exercise the sender in dry-run mode:

```powershell
.\.venv\Scripts\python.exe main.py send
```

This logs `SIMULATED`; no SMTP connection is opened. If you subsequently use `--live`, a prior `SIMULATED` record does not block the one explicit test-inbox delivery. After a successful test-inbox delivery, reruns are deduplicated by lowercase email.

Only after configuring SMTP and confirming `TEST_INBOX` is your own inbox, run:

```powershell
.\.venv\Scripts\python.exe main.py send --live
```

Generated DMs are written to `data/dm_manual_queue.csv`. They are never auto-sent. Email attempts are recorded in `data/outreach_log.csv`.

## 8. Outputs and troubleshooting

| Path | Purpose |
| --- | --- |
| `data/cache/` | Cached API responses |
| `data/raw_channels.csv` | Discovered channel IDs and source keywords |
| `data/influencers.csv` | Enriched records and filter results |
| `data/shortlist.csv` | Eligible records ordered by brand-fit score |
| `data/messages.csv` | Draft email/DM and approval flag |
| `data/outreach_log.csv` | Simulated/live/failed/duplicate email attempts |
| `data/dm_manual_queue.csv` | DMs waiting for manual review and sending |
| `logs/pipeline.log` | Pipeline diagnostics |

- `Missing required env var`: check the local `.env` spelling and restart the command.
- YouTube quota/API errors: check that YouTube Data API v3 is enabled, the key is valid, and quota remains. Cached successful pages are reused on reruns.
- Groq model error: set `personalization.model` to a currently available model on your account.
- Draft failure: check the pipeline log; failed rows are skipped rather than written as empty drafts. A fatal key/account/model error aborts the stage.
- Empty shortlist: inspect `fail_reasons` in `data/influencers.csv` and adjust configured thresholds only if appropriate.

The workflow does not scrape login-protected sites, guess contact details, or provide audience demographics unavailable from the public API.