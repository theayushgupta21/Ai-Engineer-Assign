"""Enrich discovered YouTube channels using public API fields."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from src.config import get_secret, load_config
from src.models import Influencer, NF
from src.utils.cache import JsonCache
from src.utils.logger import get_logger
from src.utils.retry import retry
from src.utils.validators import extract_email

MAX_CHANNEL_BATCH = 50


def enrich_channels(
    config: dict[str, Any] | None = None,
    service: Any | None = None,
) -> list[dict[str, Any]]:
    """Fetch channel and recent-video data, validate records, and save CSV."""
    cfg = config or load_config()
    paths = cfg["paths"]
    logger = get_logger(__name__, paths["log_file"])
    raw = pd.read_csv(paths["raw_channels"]).fillna("")
    cache = JsonCache(paths["cache_dir"])
    youtube = service or _build_youtube_service()
    records: list[dict[str, Any]] = []

    for offset in range(0, len(raw), MAX_CHANNEL_BATCH):
        batch = raw.iloc[offset : offset + MAX_CHANNEL_BATCH]
        params = {"part": "snippet,statistics,contentDetails", "id": ",".join(batch["channel_id"])}
        channels = _cached_list(cache, "channels", youtube.channels(), params).get("items", [])
        by_id = {channel["id"]: channel for channel in channels}
        for source in batch.to_dict("records"):
            channel = by_id.get(source["channel_id"])
            if not channel:
                logger.warning("Channel %s was not returned by YouTube", source["channel_id"])
                records.append(_unavailable_record(source))
                continue
            try:
                records.append(_build_record(cfg, cache, youtube, source, channel))
            except Exception as exc:
                logger.exception("Could not enrich channel %s: %s", source["channel_id"], exc)
                records.append(_unavailable_record(source))

    output = [_serialize_record(record) for record in records]
    pd.DataFrame(output).to_csv(paths["influencers"], index=False)
    logger.info("Enriched %d of %d channels", len(records), len(raw))
    return output


def _build_youtube_service() -> Any:
    """Create the official YouTube Data API v3 client."""
    from googleapiclient.discovery import build

    return build("youtube", "v3", developerKey=get_secret("YOUTUBE_API_KEY"))


def _cached_list(cache: JsonCache, endpoint: str, resource: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Execute and cache one YouTube list request."""
    key = json.dumps({"endpoint": endpoint, **params}, sort_keys=True)
    return cache.get_or_fetch(key, lambda: _execute_request(resource, params))


@retry(max_attempts=3, base_delay=1.0)
def _execute_request(resource: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Execute one retriable API list request."""
    return resource.list(**params).execute()


def _build_record(
    config: dict[str, Any], cache: JsonCache, youtube: Any,
    source: dict[str, Any], channel: dict[str, Any],
) -> dict[str, Any]:
    """Map a public channel and its recent videos into the project schema."""
    snippet = channel.get("snippet", {})
    statistics = channel.get("statistics", {})
    uploads = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    videos = _recent_videos(cache, youtube, uploads, config["enrichment"]["recent_videos"])
    description = snippet.get("description", "")
    public_text = " ".join([description, *[part for video in videos for part in _video_text(video)]])
    links = _extract_links(description)
    title_hits = _keyword_hits(config["filtering"]["niche_keywords"], public_text)
    record = {
        "id": source["channel_id"], "name": snippet.get("title", ""), "platform": "YouTube",
        "profile_url": f"https://www.youtube.com/channel/{source['channel_id']}",
        "followers": _int_or_none(statistics.get("subscriberCount")),
        "avg_views": _average([_int_or_none(video.get("statistics", {}).get("viewCount")) for video in videos]),
        "engagement_rate": _engagement_rate(videos),
        "niche": ", ".join(title_hits) if title_hits else NF,
        "content_themes": ", ".join(title_hits) if title_hits else NF,
        "recent_titles": [video.get("snippet", {}).get("title", "") for video in videos],
        "email": extract_email(description), "email_source": "channel description" if extract_email(description) != NF else NF,
        "instagram_url": links.get("instagram", NF), "website": links.get("website", NF),
        "audience_age": NF, "audience_gender": NF, "audience_geo": NF,
        "country": snippet.get("country", NF),
        "language": snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage") or NF,
        "last_upload": videos[0].get("snippet", {}).get("publishedAt") if videos else None,
        "brand_fit_score": None, "status": "UNFILTERED", "fail_reasons": [],
        "source": source.get("source_keyword", "YouTube Data API v3"),
        "fetched_at": source.get("fetched_at", ""),
    }
    return Influencer.model_validate(record).model_dump()


def _unavailable_record(source: dict[str, Any]) -> dict[str, Any]:
    """Preserve a discovered channel when enrichment cannot retrieve its data."""
    channel_id = str(source.get("channel_id", ""))
    return Influencer(
        id=channel_id,
        name=str(source.get("title") or NF),
        platform="YouTube",
        profile_url=f"https://www.youtube.com/channel/{channel_id}",
        source=str(source.get("source_keyword") or "YouTube Data API v3"),
        fetched_at=str(source.get("fetched_at", "")),
    ).model_dump()


def _recent_videos(cache: JsonCache, youtube: Any, uploads: str | None, count: int) -> list[dict[str, Any]]:
    """Fetch a channel's latest videos from its public uploads playlist."""
    if not uploads:
        return []
    playlist = _cached_list(cache, "playlistItems", youtube.playlistItems(), {
        "part": "contentDetails", "playlistId": uploads, "maxResults": min(int(count), 50),
    })
    ids = [item.get("contentDetails", {}).get("videoId") for item in playlist.get("items", [])]
    ids = [video_id for video_id in ids if video_id]
    if not ids:
        return []
    response = _cached_list(cache, "videos", youtube.videos(), {
        "part": "snippet,statistics", "id": ",".join(ids),
    })
    return response.get("items", [])


def _video_text(video: dict[str, Any]) -> list[str]:
    """Return searchable title, description, and tag text for a video."""
    snippet = video.get("snippet", {})
    return [snippet.get("title", ""), snippet.get("description", ""), " ".join(snippet.get("tags", []))]


def _extract_links(text: str) -> dict[str, str]:
    """Extract public Instagram and non-YouTube website URLs."""
    links: dict[str, str] = {}
    for url in re.findall(r"https?://[^\s<>\]\[()]+", text):
        clean_url = url.rstrip(".,;:)")
        host = urlparse(clean_url).netloc.lower().removeprefix("www.")
        if host == "instagram.com" and "instagram" not in links:
            links["instagram"] = clean_url
        elif host and not host.endswith("youtube.com") and not host.endswith("youtu.be") and "website" not in links:
            links["website"] = clean_url
    return links


def _keyword_hits(keywords: list[str], text: str) -> list[str]:
    """Return configured niche keywords present in source text."""
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lowered]


def _int_or_none(value: Any) -> int | None:
    """Convert an API count to an integer, preserving unavailable values."""
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _average(values: list[int | None]) -> float | None:
    """Calculate a mean while ignoring unavailable values."""
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _engagement_rate(videos: list[dict[str, Any]]) -> float | None:
    """Calculate mean likes-plus-comments per view for recent videos."""
    rates = []
    for video in videos:
        stats = video.get("statistics", {})
        views = _int_or_none(stats.get("viewCount"))
        likes = _int_or_none(stats.get("likeCount"))
        comments = _int_or_none(stats.get("commentCount"))
        if views and likes is not None and comments is not None:
            rates.append((likes + comments) / views)
    return sum(rates) / len(rates) if rates else None


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert list fields into stable CSV-friendly JSON strings."""
    result = record.copy()
    result["recent_titles"] = json.dumps(result["recent_titles"], ensure_ascii=True)
    result["fail_reasons"] = json.dumps(result["fail_reasons"], ensure_ascii=True)
    return result