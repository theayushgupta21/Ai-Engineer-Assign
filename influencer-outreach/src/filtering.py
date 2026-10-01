"""Apply deterministic eligibility rules and rank brand fit."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.config import load_config
from src.utils.logger import get_logger
from src.utils.validators import NOT_FOUND


def filter_influencers(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Filter all enriched rows, save results, and write a ranked shortlist."""
    cfg = config or load_config()
    paths = cfg["paths"]
    logger = get_logger(__name__, paths["log_file"])
    rows = pd.read_csv(paths["influencers"]).fillna("").to_dict("records")
    results = [filter_record(row, cfg) for row in rows]
    pd.DataFrame(results).to_csv(paths["influencers"], index=False)
    shortlist = [row for row in results if row["status"] != "FAIL"]
    shortlist.sort(key=lambda row: row["brand_fit_score"], reverse=True)
    pd.DataFrame(shortlist).to_csv(paths["shortlist"], index=False)
    counts = pd.Series([row["status"] for row in results]).value_counts().to_dict()
    logger.info("Filtering summary: %s", counts)
    return results


def filter_record(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one record and retain it with status and reasons."""
    rules = config["filtering"]
    reasons = []
    followers = _number(row.get("followers"))
    engagement = _number(row.get("engagement_rate"))
    if followers is None or not rules["min_followers"] <= followers <= rules["max_followers"]:
        reasons.append("followers outside configured range or unavailable")
    if engagement is None or engagement < rules["min_engagement_rate"]:
        reasons.append("engagement rate below threshold or unavailable")
    hits = _matching_keywords(row, rules["niche_keywords"])
    if len(hits) < rules["min_keyword_hits"]:
        reasons.append("insufficient fashion/beauty keyword matches")
    days = _days_since(row.get("last_upload"))
    if days is not None and days > rules["max_days_since_last_upload"]:
        reasons.append("last upload is older than configured activity window")
    if days is None:
        reasons.append("last upload date unavailable")
    _check_optional_locale(row, config["discovery"], reasons)
    email_missing = row.get("email", NOT_FOUND) == NOT_FOUND
    row["status"] = "FAIL" if reasons else "PASS_NO_EMAIL" if email_missing else "PASS"
    row["fail_reasons"] = json.dumps(reasons, ensure_ascii=True)
    row["brand_fit_score"] = _brand_fit_score(row, rules, len(hits), days)
    return row


def _number(value: Any) -> float | None:
    """Parse an optional numeric CSV value."""
    try:
        return float(value) if value not in (None, "", NOT_FOUND) else None
    except (TypeError, ValueError):
        return None


def _matching_keywords(row: dict[str, Any], keywords: list[str]) -> list[str]:
    """Find niche keywords in stored titles, themes, and channel text."""
    text = " ".join(str(row.get(field, "")) for field in ("niche", "content_themes", "recent_titles")).lower()
    return [keyword for keyword in keywords if keyword.lower() in text]


def _days_since(value: Any) -> int | None:
    """Return age in days for an ISO upload timestamp."""
    if not value or pd.isna(value):
        return None
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - timestamp).days)
    except ValueError:
        return None


def _check_optional_locale(row: dict[str, Any], discovery: dict[str, Any], reasons: list[str]) -> None:
    """Fail only when available location or language conflicts with configuration."""
    expected_country = discovery.get("region_code")
    expected_language = discovery.get("relevance_language")
    country = row.get("country")
    language = row.get("language")
    if country not in (None, "", NOT_FOUND) and expected_country and country != expected_country:
        reasons.append("country does not match configured region")
    if language not in (None, "", NOT_FOUND) and expected_language and language != expected_language:
        reasons.append("language does not match configured language")


def _brand_fit_score(row: dict[str, Any], rules: dict[str, Any], hits: int, days: int | None) -> float:
    """Compute a configurable weighted score from observed fields."""
    weights = rules["brand_fit_weights"]
    follower = _number(row.get("followers"))
    engagement = _number(row.get("engagement_rate"))
    follower_score = 1.0 if follower is not None and rules["min_followers"] <= follower <= rules["max_followers"] else 0.0
    engagement_score = min(1.0, engagement / rules["engagement_score_cap"]) if engagement is not None else 0.0
    niche_score = min(1.0, hits / rules["min_keyword_hits"])
    activity_score = max(0.0, 1.0 - days / rules["max_days_since_last_upload"]) if days is not None else 0.0
    weighted = (
        follower_score * weights["followers"] + engagement_score * weights["engagement"]
        + niche_score * weights["niche"] + activity_score * weights["activity"]
    )
    return round(weighted * 100, 2)