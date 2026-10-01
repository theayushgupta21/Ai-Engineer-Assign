# Influencer Outreach Pipeline

A CLI pipeline that discovers public YouTube channels in fashion and beauty, enriches public channel/video data, applies deterministic filters, drafts personalized outreach, and tracks approved email attempts. Instagram DMs are exported for manual sending only.

## Requirements and setup

- Python 3.11+
- YouTube Data API v3 key
- Groq API key for message generation

Install dependencies with `pip install -r requirements.txt`. Copy `.env.example` to `.env` and set `GROQ_API_KEY` and `YOUTUBE_API_KEY`. Never put real keys in `.env.example` or commit `.env`.

**Credential warning:** the current workspace `.env.example` contains value-present sensitive entries. Do not commit it or copy it into `.env` until those entries have been replaced with placeholders; rotate any credentials that were exposed.

The current Groq model is `openai/gpt-oss-20b`; `openai/gpt-oss-120bt` is the configured quality fallback. Request token limit, temperature, retry count, and inter-request delay are controlled in `config.yaml`.

For the full Windows setup, staged run commands, review workflow, and troubleshooting, see [SETUP_AND_RUN.md](SETUP_AND_RUN.md).

## Run

```powershell
python main.py run-all
python main.py discover
python main.py enrich
python main.py filter
python main.py personalize
python main.py send
```

Before rerunning `personalize` after a failed run, manually delete a stale `data/messages.csv` so old drafts cannot mix with the new result. The stage never deletes this file automatically.

The sender defaults to dry-run. Review `data/messages.csv` and set `approved` to `true` for drafts to send. `python main.py send --live` sends approved email drafts only to the configured `TEST_INBOX`; it does not send to influencer addresses. DMs are written to `data/dm_manual_queue.csv` and are never auto-sent.

## Pipeline and outputs

1. Discovery searches configured keywords through the official YouTube Data API v3 and writes unique channel IDs to `data/raw_channels.csv`.
2. Enrichment collects channel statistics, recent public videos, public-description emails, and public links into `data/influencers.csv`.
3. Filtering preserves every enriched row with a `PASS`, `PASS_NO_EMAIL`, or `FAIL` status and reasons. Eligible rows are ranked into `data/shortlist.csv`.
4. Personalization uses Groq and the prompt files in `prompts/`, validates word counts, and stores successful drafts in `data/messages.csv` for manual approval. Failed rows are skipped; fatal account/configuration errors abort the stage.
5. Sending deduplicates by lowercase email and tracks attempts in `data/outreach_log.csv`; generated DMs go to the manual queue.

All paths, thresholds, keywords, model names, and brand details are configured in `config.yaml`. API responses are cached under `data/cache/`; logs are written to `logs/pipeline.log`.

## Filtering defaults

| Criterion | Default ||
| --- | --- |
| Followers | 5,000–100,000 |
| Engagement | At least 1% (mean likes plus comments per view) |
| Niche | At least two configured keyword matches |
| Activity | Upload within 90 days |
| Email | Missing email yields `PASS_NO_EMAIL`, not a fabricated address |

## Limitations

- Discovery and enrichment require a valid YouTube API key and are subject to quota limits. Search results may not yield the target record count.
- YouTube does not provide audience demographics through this workflow; unavailable fields remain `Not Found`.
- Email extraction checks public channel descriptions only. No email or metric is guessed.
- Language and country checks apply only when channel metadata is available.
- LLM output can be inaccurate despite field-only prompts and word-count validation; drafts require human review and approval.
- Groq transient failures are retried with backoff. Individual exhausted/invalid drafts are skipped and logged; if every row fails, the stage exits non-zero without writing a new messages file.
- Live SMTP mode targets only the configured test inbox. Production delivery to creators is intentionally not implemented.
- No Instagram login scraping, automated DMs, demo dataset, or fabricated influencer records are included.

## Validation

Run tests with `python -m pytest -q`. Unit tests use fake API responses and temporary CSV/cache paths; no live API calls or email sending are required.