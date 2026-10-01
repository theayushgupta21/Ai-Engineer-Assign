# PRD.md: Product Requirements Document
**Project:** Automated Micro-Influencer Outreach System (EDXSO AI Engineer Intern, Assignment 1)

## 1. Overview
A modular Python pipeline that discovers real micro-influencers in the **Fashion & Beauty** niche, filters and classifies them, enriches their profiles, generates personalized email and Instagram DM outreach with an LLM, and simulates sending with a duplicate-safe tracker.

## 2. Goals
- Discover 50+ real micro-influencers (5,000-100,000 followers).
- Fully implement one filtering category (Fashion & Beauty) with explainable PASS/FAIL.
- Enrich shortlisted profiles with contact email, metrics, and content context.
- Generate genuinely personalized email (60-90 words) and DM (15-30 words).
- Provide a sending layer with dedupe, status recording, and an outreach log.
- Be modular and scalable from 50 to 500+ influencers.

## 3. Non-goals
- Scraping Instagram/TikTok behind login or bypassing platform restrictions.
- Guessing emails or inventing metrics.
- Auto-sending Instagram DMs.
- Building a UI (CLI plus optional Streamlit view is enough).

## 4. Users
- **Primary:** Evaluator reviewing the assignment.
- **Secondary:** A marketing operator who would run the tool for a brand.

## 5. Functional requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| F1 | Discover channels via YouTube Data API v3 using configurable keywords | Must |
| F2 | Collect >= 80 raw channels so 50+ remain after cleaning | Must |
| F3 | Compute subscribers, avg views/likes/comments (last 10 videos), engagement rate | Must |
| F4 | Extract email ONLY from public text (description/links); else `Not Found` | Must |
| F5 | Extract content themes from titles/descriptions/tags (keyword-based, optional LLM summary) | Must |
| F6 | Filter: follower range, min engagement, niche keyword match, language/geo, email presence; output reasons | Must |
| F7 | Brand-fit score (0-100) as a weighted rule-based score | Should |
| F8 | Groq generates email (60-90 words) + DM (15-30 words) per shortlisted influencer | Must |
| F9 | Code validates word counts and regenerates on failure | Must |
| F10 | Sender: valid email only, dry-run default, dedupe, status + log | Must |
| F11 | Instagram DM manual-send queue CSV | Must |
| F12 | Outreach tracker: Influencer, Email, Message Generated, Sent, Date, Status | Must |
| F13 | Optional audience age/gender/geo fields, marked `Not Found` if unavailable | Could |
| F14 | Optional Streamlit dashboard for review/approval | Could |

## 6. Non-functional requirements
- **Reliability:** retries, per-record error isolation, cached API responses.
- **Reproducibility:** `config.yaml` plus `.env`, one-command run.
- **Scalability:** batch processing, pagination, quota-aware.
- **Transparency:** source + timestamp on every record; limitations documented.

## 7. Filtering spec (defaults, all configurable)
| Criterion | Rule |
|-----------|------|
| Followers | 5,000 <= subs <= 100,000 |
| Engagement rate | >= 1.0% (avg (likes+comments)/views, last 10 videos) |
| Niche match | >= 2 fashion/beauty keyword hits in titles/description |
| Activity | Last upload within 90 days |
| Language/Geo | Channel language/country matches config if available; else `Not Found` (not auto-fail) |
| Email | Required for email outreach; if `Not Found`, status = `PASS_NO_EMAIL` (DM queue only) |

Statuses: `PASS`, `PASS_NO_EMAIL`, `FAIL` (with `fail_reasons`).

## 8. Data model (`influencers.csv`)
`id, name, platform, profile_url, followers, avg_views, engagement_rate, niche, content_themes, recent_titles, email, email_source, instagram_url, website, audience_age, audience_gender, audience_geo, country, language, brand_fit_score, status, fail_reasons, source, fetched_at`

**Outreach log (`outreach_log.csv`):**
`influencer_id, influencer, email, message_generated, email_subject, sent, date, status, error`

## 9. Deliverables
Working code, influencer dataset (50+), personalized messages, outreach tracker, README, demo video/screenshots, list of APIs/tools.

## 10. Success metrics
- >= 50 real records with source + timestamp
- 100% of rows have PASS/FAIL + reason
- 100% of messages within word limits
- 0 duplicate sends on re-run
- 0 fabricated emails or metrics

## 11. Risks and mitigations
| Risk | Mitigation |
|------|------------|
| Low email find rate | Document honestly; use PASS_NO_EMAIL plus DM queue |
| YouTube quota (search = 100 units/call, 10k/day) | Cache, batch, use `channels.list` (1 unit) |
| Groq transient errors | Retry with exponential backoff and `retry-after` when available |
| LLM breaks word limits | Validate and regenerate; skip/log failed rows, abort on fatal account errors |
| Non-fashion channels in results | Keyword match + brand-fit filter |
| Platform restrictions | Official APIs only; manual DM queue |

## 12. Milestones
1. Setup + config (Day 1)
2. Discovery + enrichment (Day 1-2)
3. Filtering (Day 2)
4. Personalization (Day 3)
5. Sender + tracker (Day 3)
6. README + demo (Day 4)
