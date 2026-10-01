# STRUCTURE_AND_WORKFLOW.md: Project Structure and Workflow

## 1. Tech stack
| Layer | Tool |
|-------|------|
| Language | Python 3.11+ |
| Discovery/Enrichment | YouTube Data API v3 (`google-api-python-client`) |
| Data | pandas, SQLite (optional), CSV exports |
| Validation | Pydantic |
| LLM | Groq API (model name in config) |
| Sending | SMTP / Gmail API (dry-run default) |
| Config | `config.yaml` + `.env` (`python-dotenv`) |
| Optional UI | Streamlit review page |
| Optional automation | n8n/Make wrapper calling `main.py` |

## 2. Directory structure
```
influencer-outreach/
├── RULES.md
├── PRD.md
├── AGENT_PROMPT.md
├── SETUP_AND_RUN.md
├── STRUCTURE_AND_WORKFLOW.md
├── README.md
├── requirements.txt
├── config.yaml              # keywords, thresholds, paths, model, brand info
├── .env.example             # YOUTUBE_API_KEY, GROQ_API_KEY, SMTP_*
├── .gitignore
├── main.py                  # CLI orchestration only
├── src/
│   ├── discovery.py         # keyword search -> raw channels
│   ├── enrichment.py        # stats, engagement, email/link extraction, themes
│   ├── filtering.py         # PASS/FAIL + reasons + brand-fit score
│   ├── personalize.py       # LLM email + DM generation and validation
│   ├── sender.py            # dry-run/SMTP send, dedupe, log, DM queue
│   ├── models.py            # Pydantic schemas
│   └── utils/
│       ├── logger.py
│       ├── retry.py
│       ├── cache.py
│       └── validators.py    # email regex, word counts
├── prompts/
│   ├── system.txt
│   ├── outreach_user.txt
│   └── retry_suffix.txt
├── data/
│   ├── cache/
│   ├── raw_channels.csv
│   ├── influencers.csv      # full dataset with status + reasons
│   ├── shortlist.csv
│   ├── messages.csv
│   ├── outreach_log.csv     # tracker
│   └── dm_manual_queue.csv
├── logs/pipeline.log
├── tests/                   # validators, filtering, dedupe tests
└── docs/                    # screenshots, demo video link
```

## 3. Pipeline workflow
```
Discovery -> Enrichment -> Filtering -> AI Personalization
   -> Review -> Sending -> Tracking
```

| # | Stage | Input | Output | Key logic |
|---|-------|-------|--------|-----------|
| 1 | Discovery | keywords (config) | raw_channels.csv (target configured in YAML) | search.list, paginate, dedupe by channel_id, cache |
| 2 | Collection/Enrichment | raw channel IDs | enriched rows | subs, last 10 videos, engagement rate, email regex, social links, themes |
| 3 | Filtering | enriched rows | influencers.csv | range, engagement, niche match, activity, email; PASS / PASS_NO_EMAIL / FAIL + reasons |
| 4 | Shortlist | influencers.csv | shortlist.csv | status != FAIL, sorted by brand-fit score |
| 5 | Personalization | shortlist | messages.csv | Groq JSON chat completion, word-count validation, configured delay and retries |
| 6 | Review | messages.csv | approved flag | manual CSV approval before sending |
| 7 | Sending | approved + valid email | outreach_log.csv | dedupe, dry-run/SMTP, status; DMs to manual queue |
| 8 | Tracking | log | summary report | counts by status, duplicates blocked |

## 4. Build order (matches AGENT_PROMPT.md)
1. Skeleton, config, utils
2. `discovery.py`
3. `enrichment.py`
4. `filtering.py`
5. `personalize.py`
6. `sender.py`
7. `main.py`, tests, README, demo

## 5. CLI usage
```bash
python main.py run-all
python main.py discover
python main.py enrich
python main.py filter
python main.py personalize
python main.py send
python main.py send --live  # explicitly sends only to TEST_INBOX
```

## 6. Error-handling map
| Failure | Behavior |
|---------|----------|
| API quota/HTTP error | retry x3 with backoff, log, resume from cache |
| Missing email/field | `"Not Found"`, continue |
| Invalid email format | treat as `Not Found` |
| Groq transient error | retry x3 with exponential backoff and `retry-after` when supplied |
| Groq auth/permission/account or general bad request | abort personalization with a clear error |
| Row-scoped Groq JSON validation error | retry, then skip and log that row |
| Draft out-of-range length or per-row failure | retry configured validation attempts; skip and log the row |
| Every personalization row fails | exit non-zero and do not write an empty messages file |
| Duplicate email | skip, log `SKIPPED_DUPLICATE` |
| SMTP failure | log `FAILED` + error, continue |

## 7. Scalability notes
- Keyword list and thresholds are config-driven, so scaling to 500+ is a config change.
- Cached API calls and batched `channels.list` (50 IDs per call) save quota.
- Stages are independent and idempotent, so they can run as separate n8n/Make nodes or cron jobs.
- SQLite can replace CSV with no change to stage interfaces.
- Current personalization model: `openai/gpt-oss-20b`; config notes `openai/gpt-oss-120bt` as a quality fallback.

## 8. README template
1. Overview and architecture diagram
2. Tech stack and APIs
3. Data sources and discovery method
4. Filtering logic (thresholds table)
5. Enrichment process and email-extraction policy
6. AI model and prompts
7. Personalization logic
8. Sending mechanism and dedupe
9. Limitations (low email rate, no audience demographics, no IG auto-DM)
10. Setup and run instructions
11. Sample outputs and demo link
