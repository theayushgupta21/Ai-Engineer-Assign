# AGENT_PROMPT.md: Prompts for the AI Coding Agent and the Runtime LLM

## Part A: Master prompt for the vibe-coding agent (paste at session start)

```
You are a senior Python engineer helping me build the "Automated Micro-Influencer
Outreach System" (EDXSO Assignment 1).

Before doing anything, read these files in order:
1. RULES.md   (mandatory guardrails)
2. PRD.md     (what to build)
3. STRUCTURE_AND_WORKFLOW.md (architecture and pipeline)

Hard constraints:
- Never fabricate influencers, emails, or metrics. Use "Not Found" when data is missing.
- Use only the official YouTube Data API v3. No scraping behind logins.
- Instagram DMs are never auto-sent; write them to a manual queue CSV.
- Email sending defaults to dry-run.

How to work:
- Build ONE module at a time in the order given in STRUCTURE_AND_WORKFLOW.md.
- After each module: show the code, explain it in 3-5 lines, run it, show real output.
- Write a small test for each module.
- Ask me before assuming anything unclear.
- Keep everything config-driven (config.yaml) and secrets in .env.

Start with: project skeleton, config.yaml, .env.example, requirements.txt,
and src/utils (logger, retry decorator, cache helper). Then stop and wait for my approval.
```

## Part B: Per-module task prompts (use one at a time)

**B1 Discovery**
```
Implement src/discovery.py. Use YouTube Data API v3 search.list for each keyword in
config.yaml (type=channel and type=video to surface channel IDs). Paginate. Dedupe by
channel_id. Cache responses. Save data/raw_channels.csv with channel_id, title, source
keyword, fetched_at. Target 80-100 channels. Handle quota and HTTP errors gracefully.
```

**B2 Enrichment**
```
Implement src/enrichment.py. For each channel_id: call channels.list (snippet, statistics,
brandingSettings), then fetch the last 10 videos (playlistItems + videos.list) for views,
likes, comments, titles, tags. Compute engagement_rate = mean((likes+comments)/views).
Extract emails ONLY via regex from the public description. Extract Instagram/website links
from the description. Anything missing = "Not Found". Validate each record with Pydantic.
```

**B3 Filtering**
```
Implement src/filtering.py. Apply the rules in PRD.md section 7 from config.yaml. Output
status (PASS / PASS_NO_EMAIL / FAIL) and a fail_reasons list per row, plus a brand_fit_score
0-100. Never drop rows. Write data/influencers.csv and print a summary table.
```

**B4 Personalization**
```
Implement src/personalize.py. For each PASS / PASS_NO_EMAIL row, call Groq using the
prompts in prompts/. Use the model, request limits, and delay configured in config.yaml.
Email must be 60-90 words and DM 15-30 words. Retry transient API errors, regenerate invalid
messages up to the configured limit, then log and skip that row. Abort immediately on fatal
authentication, permission, or account errors. If all rows fail, exit non-zero without writing
empty drafts. Use only stored fields and vary the collaboration angle.
Save to data/messages.csv.
```

**B5 Sender**
```
Implement src/sender.py. Select rows with a valid email and an approved message. Dedupe
against data/outreach_log.csv. In DRY_RUN mode, log "SIMULATED". Otherwise send via SMTP
to the configured test inbox. Write DMs to data/dm_manual_queue.csv. Log every attempt with
status and error.
```

**B6 Orchestration and docs**
```
Implement main.py (CLI: run all or single stage) and finish README.md using the template
in STRUCTURE_AND_WORKFLOW.md. Include honest limitations.
```

## Part C: Runtime prompts

The prompt files in `prompts/` are the only runtime source of prompt wording. Keep their
placeholders aligned with `_prompt_values` in `src/personalize.py`; the user prompt must
explicitly request JSON for Groq's JSON response mode. Do not duplicate alternate runtime
templates in this document.

**Collaboration angle selection (code, not LLM):** map by rules, e.g. engagement >= 4% -> UGC, 2-4% -> affiliate, < 2% with high reach -> paid placement, small but niche -> barter. This guarantees variety and keeps it explainable.
