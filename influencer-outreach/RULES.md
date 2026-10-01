# RULES.md: AI Agent Rules (Vibe-Coding Guardrails)

The AI coding agent MUST read this file first, every session, before writing or editing code.

## 1. Non-negotiable data integrity rules
1. NEVER fabricate influencers, emails, follower counts, engagement rates, or demographics.
2. NEVER guess or pattern-generate an email (e.g. `name@gmail.com`). Emails come ONLY from a real public source (channel description, linked website contact page, public business-email field). Otherwise the value is exactly `"Not Found"`.
3. Missing data is stored as `"Not Found"` (text fields) or `null` (numeric fields). Never a placeholder number.
4. Every record stores `source` (where it came from) and `fetched_at` (ISO timestamp).
5. No mock/sample data in the final dataset. Fixtures are allowed ONLY in `tests/` and must be labelled `FAKE_FIXTURE`.

## 2. Platform and legal rules
1. Use only official APIs or permitted public data (YouTube Data API v3). No login-wall scraping, no bypassing rate limits or anti-bot protection.
2. Instagram DMs are NEVER auto-sent. They go to `data/dm_manual_queue.csv` for manual sending.
3. Email sending defaults to `DRY_RUN=true`. Real sending requires an explicit flag and a test inbox first.
4. Respect API quotas. Cache every API response in `data/cache/` so nothing is fetched twice.

## 3. Coding rules
1. Python 3.11+, type hints on all functions, docstrings on all public functions.
2. One responsibility per module (see STRUCTURE_AND_WORKFLOW.md). No logic in `main.py` beyond orchestration.
3. All thresholds, keywords, paths, and model names live in `config.yaml`. No magic numbers in code.
4. Secrets live in `.env` only. Never hardcode or log keys. `.env` is in `.gitignore`; `.env.example` is committed.
5. Retry transient external errors with exponential backoff (maximum 3 attempts) and log failures. Do not retry authentication, permission, account, or general malformed-request errors; the recognized row-scoped Groq JSON-validation error may be retried before that row is skipped. Fatal configuration/account errors may abort the stage.
6. Use `logging`, not `print`. Logs go to `logs/pipeline.log`.
7. Each stage is idempotent: re-running it must not duplicate rows or re-send emails.
8. Use pandas for tabular work, SQLite (or CSV) for storage, Pydantic for record validation.
9. Keep functions small (< 40 lines). No dead code, no unused imports.

## 4. Filtering rules
1. Every influencer gets `status` = `PASS` or `FAIL` and a human-readable `fail_reasons` list. Never drop a row silently.
2. Filtering is deterministic and rule-based. The LLM is NOT used to decide pass/fail on numbers.

## 5. LLM / message rules
1. Personalize only from real stored fields (name, niche, recent video titles, content themes, tone). Never invent "recent content" the influencer did not post.
2. Email: 60-90 words. DM: 15-30 words. Validate in code and regenerate up to the configured limit. If a row still fails, log and skip it rather than writing an empty or placeholder draft. If all rows fail, exit non-zero and do not write an empty messages file.
3. No fake claims about the brand, pricing, or past relationship with the influencer.
4. Vary the collaboration angle by influencer (sponsorship, affiliate, UGC, ambassador, barter). No single fixed template.
5. The prompt lives in `prompts/` as files, not inline strings.

## 6. Sending rules
1. Send only when `email != "Not Found"`, the email passes regex validation, and the message is approved.
2. Dedupe by lowercase email against `outreach_log.csv` BEFORE sending.
3. Always write a log row: influencer, email, message_generated, sent, date, status, error.

## 7. Workflow rules for the agent
1. Work in small steps: one module at a time, run it, show the output, then move on.
2. After each module, write or run a minimal test.
3. If requirements are unclear, ask. Do not assume.
4. Never modify files outside the project directory. Never delete `data/` without confirmation.
5. Update README.md whenever behavior, setup, or limitations change.
6. Be honest: if something cannot be done legitimately (e.g. auto-DM on Instagram), document it under Limitations.

## 8. Definition of Done
- [ ] 50+ real influencers in dataset, each with source + timestamp
- [ ] Every row has PASS/FAIL + reason
- [ ] Shortlist enriched; unknown emails marked `Not Found`
- [ ] Email + DM generated and word-count validated
- [ ] Sender works in dry-run, dedupes, logs
- [ ] README complete; demo video or screenshots ready
