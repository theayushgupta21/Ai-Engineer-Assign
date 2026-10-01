# Influencer Outreach Pipeline

A lightweight AI-powered outreach workflow for identifying relevant creator prospects, enriching their public data, filtering for quality leads, and generating personalized outreach drafts for manual approval.

This project is organized as a command-line pipeline and is located under [influencer-outreach/](influencer-outreach/). The main entrypoint, configuration, prompts, data files, and tests live there.

## Why this project

- Finds publicYouTube creators in fashion and beauty niches
- Enriches profiles with public metadata, recent videos, and email signals
- Applies deterministic quality filters before outreach
- Generates personalized email drafts using Groq-backed prompts
- Tracks outbound attempts and keeps manual approval in the loop
- Exports Instagram DMs to a manual queue instead of auto-sending

## Core workflow

1. Discovery searches YouTube by configured keywords and stores unique channel IDs.
2. Enrichment collects public stats, recent videos, and available contact details.
3. Filtering ranks eligible creators based on quality criteria and niche fit.
4. Personalization writes tailored outreach drafts for human review.
5. Sending only carries out approved drafts in dry-run or test inbox mode.

## Project structure

```text
Ai Engineer Assign/
├── README.md
├── influencer-outreach/
│   ├── main.py
│   ├── config.yaml
│   ├── requirements.txt
│   ├── AGENT_PROMPT.md
│   ├── PRD.md
│   ├── RULES.md
│   ├── SETUP_AND_RUN.md
│   ├── STRUCTURE_AND_WORKFLOW.md
│   ├── data/
│   ├── prompts/
│   ├── src/
│   └── tests/
└── ...
```

## Requirements

- Python 3.11+
- YouTube Data API v3 key
- Groq API key for message generation

## Setup

Install dependencies:

```bash
cd influencer-outreach
pip install -r requirements.txt
```

Create your environment file and set the required variables:

```bash
copy .env.example .env
```

Then populate the keys in `.env` for:

- `GROQ_API_KEY`
- `YOUTUBE_API_KEY`

> Important: never commit `.env` or add real credentials into `.env.example`. The workspace may contain sensitive values that should be rotated if exposed.

For full Windows setup instructions and a staged run guide, see [influencer-outreach/SETUP_AND_RUN.md](influencer-outreach/SETUP_AND_RUN.md).

## Run commands

```powershell
cd influencer-outreach
python main.py run-all
python main.py discover
python main.py enrich
python main.py filter
python main.py personalize
python main.py send
```

### Sending behavior

- The sender defaults to dry-run mode.
- Review `data/messages.csv` and set `approved` to `true` for drafts to be sent.
- `python main.py send --live` sends only approved drafts to the configured `TEST_INBOX`.
- DMs are written to `data/dm_manual_queue.csv` and are never auto-sent.
- Before rerunning personalization after a failed run, remove stale `data/messages.csv` content so old drafts do not mix with the new result.

## Data flow and outputs

- `data/raw_channels.csv` stores discovered channels
- `data/influencers.csv` stores enriched creator profiles
- `data/shortlist.csv` stores ranked, filtered candidates
- `data/messages.csv` stores personalized drafts awaiting approval
- `data/outreach_log.csv` tracks send attempts and deduplication
- `data/cache/` stores API responses
- `logs/pipeline.log` stores execution logs

Everything from keywords and thresholds to model names and brand details is configured in `config.yaml`.

## Filtering defaults

| Criterion | Default |
| --- | --- |
| Followers | 5,000–100,000 |
| Engagement | At least 1% (mean likes + comments per view) |
| Niche | At least two configured keyword matches |
| Activity | Uploaded within 90 days |
| Email | Missing email yields `PASS_NO_EMAIL`, not a fabricated address |

## Safety and limitations

- Discovery and enrichment depend on an active YouTube API key and quota availability.
- Audience demographics are not provided through this workflow and may remain `Not Found`.
- Email extraction is limited to public channel descriptions and never fabricates contact data.
- Language and country checks are only applied when metadata is available.
- LLM-generated drafts can still be inaccurate, so human review is required.
- Groq transient failures are retried with backoff, but exhausted or invalid drafts are skipped and logged.
- Live email mode is intentionally restricted to the configured test inbox.
- Instagram DM automation is not included, and no fabricated influencer records are created.

## Validation

Run the test suite with:

```bash
cd influencer-outreach
python -m pytest -q
```

These tests use fake API responses and temporary CSV/cache paths, so they do not require live API calls or outbound email sending.

## Recommendations

- Keep `.env` separate from the repository and rotate credentials if they have been exposed.
- Review the generated draft list before sending anything live.
- Use the staged workflow in [influencer-outreach/SETUP_AND_RUN.md](influencer-outreach/SETUP_AND_RUN.md) for a smoother Windows setup and troubleshooting flow.

This pipeline is intended for controlled, review-based outreach rather than fully automated bulk contact sending.