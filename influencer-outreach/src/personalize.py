"""Generate personalized outreach drafts from stored influencer fields."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import ROOT, load_config
from src.utils.logger import get_logger
from src.utils.retry import is_groq_fatal_error, is_groq_transient_error, retry
from src.utils.validators import NOT_FOUND, within_words, word_count


def personalize_messages(
    config: dict[str, Any] | None = None,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    """Generate and save drafts for every non-failed influencer in the shortlist."""
    cfg = config or load_config()
    paths = cfg["paths"]
    logger = get_logger(__name__, paths["log_file"])
    shortlist = pd.read_csv(paths["shortlist"]).fillna("").to_dict("records")
    eligible = [row for row in shortlist if row.get("status") in ("PASS", "PASS_NO_EMAIL")]
    if not eligible:
        pd.DataFrame(columns=_OUTPUT_COLUMNS).to_csv(paths["messages"], index=False)
        return []
    try:
        llm = client or _build_client()
    except Exception as exc:
        logger.error("Could not initialize Groq client: %s", exc)
        raise RuntimeError("Could not initialize Groq. Check GROQ_API_KEY in the local .env file.") from exc
    prompts = _load_prompts()
    output = []
    failures = 0
    delay = float(cfg["personalization"].get("delay_between_requests_seconds", 2))
    for index, row in enumerate(eligible):
        try:
            output.append(_personalize_one(row, cfg, llm, prompts))
        except Exception as exc:
            if is_groq_fatal_error(exc):
                logger.error("Fatal Groq error; aborting personalization: %s", exc)
                raise RuntimeError(f"Fatal Groq API error; personalization aborted: {exc}") from exc
            failures += 1
            logger.error("Draft failed for %s: %s", row.get("id"), exc)
        if delay > 0 and index < len(eligible) - 1:
            time.sleep(delay)
    if eligible and not output:
        logger.error("Generated 0/%d drafts (%d failed); all rows failed, no drafts were written", len(eligible), failures)
        raise SystemExit(1)
    logger.info("Generated %d/%d drafts (%d failed)", len(output), len(eligible), failures)
    pd.DataFrame(output, columns=_OUTPUT_COLUMNS).to_csv(paths["messages"], index=False)
    return output


_OUTPUT_COLUMNS = [
    "influencer_id", "influencer", "email", "subject", "email_message", "dm",
    "collab_angle", "message_status", "approved",
]


def _build_client() -> Any:
    """Create the Groq client using the key loaded from .env."""
    from groq import Groq

    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is missing")
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def _load_prompts() -> tuple[str, str, str]:
    """Read the prompt templates stored under prompts/."""
    prompt_dir = ROOT / "prompts"
    return tuple((prompt_dir / name).read_text(encoding="utf-8") for name in (
        "system.txt", "outreach_user.txt", "retry_suffix.txt",
    ))


def _personalize_one(
    row: dict[str, Any], config: dict[str, Any], client: Any,
    prompts: tuple[str, str, str],
) -> dict[str, Any]:
    """Generate one draft, enforcing configured word counts before saving."""
    system_prompt, user_template, retry_suffix = prompts
    angle = _collaboration_angle(row, config["collaboration"])
    prompt_values = _prompt_values(row, config, angle)
    user_prompt = user_template.format(**prompt_values)
    email_bounds = tuple(config["personalization"]["email_words"])
    dm_bounds = tuple(config["personalization"]["dm_words"])
    max_attempts = int(config["personalization"]["max_retries"])
    delay = float(config["personalization"].get("delay_between_requests_seconds", 2))
    last_result: dict[str, str] = {"subject": "", "email": "", "dm": ""}
    for attempt in range(max_attempts):
        response = _request_message(
            client,
            config["personalization"]["model"],
            system_prompt,
            user_prompt,
            int(config["personalization"]["max_tokens"]),
            float(config["personalization"]["temperature"]),
        )
        last_result = _parse_response(response)
        if _valid_draft(last_result, email_bounds, dm_bounds):
            return _draft_record(row, angle, last_result, "PENDING_APPROVAL")
        if attempt < max_attempts - 1:
            user_prompt += "\n" + retry_suffix.format(
                email_words=word_count(last_result.get("email", "")),
                dm_words=word_count(last_result.get("dm", "")),
            )
            if delay > 0:
                time.sleep(delay)
    raise ValueError("Groq responses did not meet the configured message format and word limits")


@retry(max_attempts=3, base_delay=1.0, retry_if=is_groq_transient_error)
def _request_message(
    client: Any, model: str, system_prompt: str, user_prompt: str,
    max_tokens: int, temperature: float,
) -> str:
    """Call Groq chat completions, retrying only transient provider errors."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        reasoning_effort="low",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def _prompt_values(row: dict[str, Any], config: dict[str, Any], angle: str) -> dict[str, str]:
    """Render only facts already present in the influencer and brand records."""
    return {
        "name": str(row.get("name") or NOT_FOUND),
        "platform": str(row.get("platform") or NOT_FOUND),
        "niche": str(row.get("niche") or NOT_FOUND),
        "content_themes": str(row.get("content_themes") or NOT_FOUND),
        "recent_titles": _titles(row.get("recent_titles")),
        "brand_name": config["brand"]["name"],
        "brand_product": config["brand"]["product"],
        "collab_angle": angle,
        "value_prop": config["brand"]["value_prop"],
    }


def _titles(value: Any) -> str:
    """Convert stored recent-title data into concise prompt text."""
    try:
        titles = json.loads(value) if isinstance(value, str) else value
        return "; ".join(str(title) for title in titles) if titles else NOT_FOUND
    except (json.JSONDecodeError, TypeError):
        return str(value) if value else NOT_FOUND


def _collaboration_angle(row: dict[str, Any], rules: dict[str, Any]) -> str:
    """Choose the collaboration angle deterministically from observed metrics."""
    engagement = _optional_float(row.get("engagement_rate"))
    followers = _optional_float(row.get("followers"))
    views = _optional_float(row.get("avg_views"))
    if engagement is not None and engagement >= rules["high_engagement_rate"]:
        return rules["high_engagement_angle"]
    if engagement is not None and engagement >= rules["mid_engagement_rate"]:
        return rules["mid_engagement_angle"]
    if (
        (followers is not None and followers >= rules["high_reach_followers"])
        or (views is not None and views >= rules["high_reach_views"])
    ):
        return rules["high_reach_angle"]
    return rules["default_angle"]


def _optional_float(value: Any) -> float | None:
    """Parse an optional numeric CSV value."""
    try:
        return float(value) if value not in (None, "", NOT_FOUND) else None
    except (TypeError, ValueError):
        return None


def _parse_response(response: str) -> dict[str, str]:
    """Parse the LLM's JSON result, returning empty fields on malformed output."""
    try:
        parsed = json.loads(response)
        return {key: str(parsed.get(key, "")).strip() for key in ("subject", "email", "dm")}
    except (json.JSONDecodeError, AttributeError):
        return {"subject": "", "email": "", "dm": ""}


def _valid_draft(result: dict[str, str], email_bounds: tuple[int, int], dm_bounds: tuple[int, int]) -> bool:
    """Check subject and message lengths against prompt requirements."""
    return (
        bool(result["subject"])
        and word_count(result["subject"]) <= 8
        and within_words(result["email"], email_bounds)
        and within_words(result["dm"], dm_bounds)
    )


def _draft_record(row: dict[str, Any], angle: str, result: dict[str, str], status: str) -> dict[str, Any]:
    """Combine a generated message with its source influencer identity."""
    return {
        "influencer_id": row.get("id", ""), "influencer": row.get("name", ""),
        "email": row.get("email", NOT_FOUND), "subject": result["subject"],
        "email_message": result["email"], "dm": result["dm"], "collab_angle": angle,
        "message_status": status, "approved": False,
    }

