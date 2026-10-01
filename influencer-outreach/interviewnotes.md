# Interview Notes: Influencer Outreach Pipeline

Personal prep sheet. Verify every "check in code" item against your own source before the interview.

## 30-second pitch

I built a CLI pipeline that finds YouTube creators in the fashion and beauty niche, enriches their public data, filters them with deterministic quality rules, and uses an LLM (Groq) to write personalized email and DM drafts. Nothing is sent without human approval, and live sending is limited to a test inbox. The interesting engineering was reliability: caching, retry logic, error classification, and validating LLM output.

## Architecture

```
discover -> enrich -> filter -> personalize -> send
   |          |         |           |            |
raw_channels  influencers  shortlist  messages   outreach_log
   .csv         .csv        .csv       .csv        .csv
        (all API responses cached in data/cache)
```

| Stage | What it does | Key design choice |
|---|---|---|
| discover | YouTube search per keyword, dedupe channel IDs | `region_code`, `relevance_language` to stay in-niche |
| enrich | Channel stats, last 10 videos, email from public description | Never fabricate emails: missing email -> `PASS_NO_EMAIL` |
| filter | Followers, engagement, niche keywords, recency, then rank | Deterministic, no LLM involved |
| personalize | LLM writes subject, email, DM | Word-limit validation, JSON output, skip failed rows |
| send | Sends approved drafts | Dry-run default, test inbox only, dedup log |

## Filtering (check in code: `src/filter*.py`)

Hard gates from `config.yaml`:
- followers between 5,000 and 100,000
- engagement rate >= 1% (mean likes + comments per view)
- at least 2 niche keyword hits
- last upload within 90 days

Ranking uses `brand_fit_weights`: followers 0.20, engagement 0.35, niche 0.25, activity 0.20. Engagement is capped at `engagement_score_cap` (5%) so one viral outlier does not dominate. Be ready to explain why engagement has the highest weight: for a brand, an engaged small audience converts better than a large passive one.

## Retry and error handling (`src/utils/retry.py`)

Three categories of Groq errors:

1. **Transient** (429, 5xx, timeouts, connection errors): retry with exponential backoff (1s, 2s, 4s). On 429, respect the `Retry-After` header if present.
2. **Per-row** (400 `json_validate_failed`): one bad generation. Retry, and if it still fails, skip that row and log it. Do not abort the batch.
3. **Fatal** (401, 402, 403, 404, other 400s): bad key, no credits, no model access, wrong model name. Abort the whole stage immediately, because retrying 26 times cannot fix a config problem.

Also: if every row fails, the stage exits non-zero and logs `Generated 0/N drafts`. It never reports success when nothing succeeded.

**Story to tell:** the first version retried a billing error (HTTP 400) three times per influencer, wasted time, and still printed "Generated 26 drafts" with zero real drafts. Fixing that taught me to classify errors by who can fix them (retry, skip, or abort) and to make the final status honest.

## Why the reasoning model needed a bigger max_tokens

`openai/gpt-oss-*` are reasoning models. They spend tokens on hidden reasoning before the visible answer, and both count against `max_tokens`. With `max_tokens: 700` the model used its whole budget thinking, the visible JSON came back empty, and Groq returned `json_validate_failed` with `failed_generation: ''`. Fix: raise `max_tokens` (2000) and set `reasoning_effort="low"` so more of the budget goes to the answer.

## Groq migration story

Started on the Anthropic API, credits ran out, migrated to Groq's free tier.
- Message format differs: system prompt moves into the `messages` list, response read from `choices[0].message.content`.
- Model names change: `llama-3.3-70b-versatile` returned 404 for my key, so I listed available models with `client.models.list()` and chose `openai/gpt-oss-20b`.
- Free tier means rate limits, so there is a `delay_between_requests_seconds` setting and 429 handling.

## Testing

17 pytest tests with fake API responses and temp CSV/cache paths, so no live calls or emails. A fake `groq` module is injected via `monkeypatch`. One test caught a real regression when I changed error classification (a missing class in the fake module made the fatal check silently return False).

## Honest limitations (say these before they ask)

- YouTube API does not expose emails, so 18 of 26 shortlisted creators had none. Those go to a manual DM queue.
- No audience demographics.
- Live sending is restricted to a test inbox, so I have no real reply-rate data.
- LLM drafts can be generic or inaccurate, which is why human approval exists.

## Likely questions

**Why deterministic filtering instead of asking the LLM to pick creators?**
Reproducible, cheap, explainable, and no API cost per channel. LLM is used only where language generation adds value.

**How do you stop the LLM from inventing facts?**
It only receives real fields (channel name, recent video titles, stats). Output is validated for JSON shape and word limits. A human approves everything.

**How would you scale this?**
Async or batched requests, a queue, a real database instead of CSVs, per-provider rate limiters, and storing prompt/model versions with each draft.

**What would you improve next?**
Placeholder guard (fail if `YOUR_BRAND` is still in config), sign-off from config, an eval set for draft quality, and open/reply tracking.

**Did you use AI tools to build it?**
Be honest: yes, I used AI assistance for scaffolding, and I debugged and changed the parts above myself. Be ready to open any file and explain it.

## Self-check before the interview

- [ ] I can explain every function in `retry.py` and `personalize.py`
- [ ] I know the exact scoring formula in the filter module
- [ ] I can run `pytest` and the pipeline live in under 5 minutes
- [ ] I have the real numbers: raw channels, shortlist size, drafts generated
- [ ] No secrets in the repo or its git history