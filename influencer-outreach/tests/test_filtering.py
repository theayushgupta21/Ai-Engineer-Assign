from datetime import datetime, timezone

from src.filtering import filter_record


def _config():
    return {
        "discovery": {"region_code": "IN", "relevance_language": "en"},
        "filtering": {
            "min_followers": 5000,
            "max_followers": 100000,
            "min_engagement_rate": 0.01,
            "min_keyword_hits": 2,
            "max_days_since_last_upload": 90,
            "engagement_score_cap": 0.05,
            "brand_fit_weights": {"followers": 0.2, "engagement": 0.35, "niche": 0.25, "activity": 0.2},
            "niche_keywords": ["fashion", "skincare", "beauty"],
        },
    }


def test_filter_record_passes_without_email():
    row = {
        "followers": 20000,
        "engagement_rate": 0.03,
        "niche": "fashion, skincare",
        "content_themes": "beauty",
        "recent_titles": "[]",
        "last_upload": datetime.now(timezone.utc).isoformat(),
        "email": "Not Found",
        "country": "IN",
        "language": "en",
    }
    result = filter_record(row, _config())
    assert result["status"] == "PASS_NO_EMAIL"
    assert result["fail_reasons"] == "[]"
    assert 0 <= result["brand_fit_score"] <= 100


def test_filter_record_keeps_fail_reason():
    result = filter_record({"followers": 100, "email": "Not Found"}, _config())
    assert result["status"] == "FAIL"
    assert "followers outside configured range or unavailable" in result["fail_reasons"]