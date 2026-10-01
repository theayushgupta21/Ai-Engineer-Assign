"""Discover YouTube channels from configured keywords."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from googleapiclient.discovery import build

from src.config import get_secret, load_config
from src.utils.cache import JsonCache
from src.utils.logger import get_logger
from src.utils.retry import retry

API_MAX_RESULTS = 50
OUTPUT_COLUMNS = ["channel_id", "title", "source_keyword", "fetched_at"]


def discover_channels(
    config: dict[str, Any] | None = None,
    service: Any | None = None,
) -> list[dict[str, str]]:
    """Search configured keywords, cache API pages, and save unique channels."""
    cfg = config or load_config()
    paths = cfg["paths"]
    logger = get_logger(__name__, paths["log_file"])
    cache = JsonCache(paths["cache_dir"])
    youtube = service or _build_youtube_service()
    target = int(cfg["discovery"]["target_raw_channels"])
    records: dict[str, dict[str, str]] = {}

    for keyword in cfg["discovery"]["keywords"]:
        for result_type in ("channel", "video"):
            page_token = None
            while len(records) < target:
                params = _search_params(cfg, keyword, result_type, page_token)
                cache_key = json.dumps(params, sort_keys=True)
                try:
                    response = cache.get_or_fetch(
                        cache_key, lambda: _execute_search(youtube, params)
                    )
                except Exception as exc:
                    logger.error("YouTube search failed for %r (%s): %s", keyword, result_type, exc)
                    break

                _add_channels(records, response, keyword, result_type)
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            if len(records) >= target:
                break
        if len(records) >= target:
            break

    channels = list(records.values())
    output_path = paths["raw_channels"]
    pd.DataFrame(channels, columns=OUTPUT_COLUMNS).to_csv(output_path, index=False)
    logger.info("Discovered %d unique channels; wrote %s", len(channels), output_path)
    return channels


def _build_youtube_service() -> Any:
    """Create the official YouTube Data API v3 client."""
    return build("youtube", "v3", developerKey=get_secret("YOUTUBE_API_KEY"))


def _search_params(
    config: dict[str, Any], keyword: str, result_type: str, page_token: str | None
) -> dict[str, Any]:
    """Build one valid search.list request from configuration."""
    discovery = config["discovery"]
    params: dict[str, Any] = {
        "part": "snippet",
        "q": keyword,
        "type": result_type,
        "maxResults": min(int(discovery["max_results_per_keyword"]), API_MAX_RESULTS),
    }
    for key in ("region_code", "relevance_language"):
        value = discovery.get(key)
        if value:
            params["regionCode" if key == "region_code" else "relevanceLanguage"] = value
    if page_token:
        params["pageToken"] = page_token
    return params


@retry(max_attempts=3, base_delay=1.0)
def _execute_search(service: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Execute one retriable YouTube search request."""
    return service.search().list(**params).execute()


def _add_channels(
    records: dict[str, dict[str, str]],
    response: dict[str, Any],
    keyword: str,
    result_type: str,
) -> None:
    """Extract channel IDs from channel and video search results."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        item_id = item.get("id", {})
        channel_id = item_id.get("channelId") if result_type == "channel" else snippet.get("channelId")
        if channel_id and channel_id not in records:
            records[channel_id] = {
                "channel_id": channel_id,
                "title": snippet.get("channelTitle") if result_type == "video" else snippet.get("title", ""),
                "source_keyword": keyword,
                "fetched_at": fetched_at,
            }