"""Pydantic schemas. Missing data is 'Not Found' (text) or None (numbers)."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

NF = "Not Found"


class Influencer(BaseModel):
    id: str
    name: str
    platform: str = "YouTube"
    profile_url: str
    followers: Optional[int] = None
    avg_views: Optional[float] = None
    engagement_rate: Optional[float] = None
    niche: str = NF
    content_themes: str = NF
    recent_titles: list[str] = Field(default_factory=list)
    email: str = NF
    email_source: str = NF
    instagram_url: str = NF
    website: str = NF
    audience_age: str = NF
    audience_gender: str = NF
    audience_geo: str = NF
    country: str = NF
    language: str = NF
    last_upload: Optional[str] = None
    brand_fit_score: Optional[float] = None
    status: str = "UNFILTERED"      # PASS | PASS_NO_EMAIL | FAIL
    fail_reasons: list[str] = Field(default_factory=list)
    source: str
    fetched_at: str
