import json
import sys
from types import ModuleType
from types import SimpleNamespace

import pandas as pd
import pytest

from src.enrichment import enrich_channels
from src.personalize import _personalize_one, _request_message, personalize_messages
from src.sender import send_outreach


class FakeRequest:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeResource:
    def __init__(self, response):
        self.response = response

    def list(self, **params):
        return FakeRequest(self.response)


class FakeYouTube:
    def channels(self):
        return FakeResource({"items": [{
            "id": "UC_FAKE_FIXTURE",
            "snippet": {
                "title": "FAKE_FIXTURE Creator",
                "description": "Business: hello@creator.test https://instagram.com/creator https://brand.test/contact",
                "country": "IN",
                "defaultLanguage": "en",
            },
            "statistics": {"subscriberCount": "20000"},
            "contentDetails": {"relatedPlaylists": {"uploads": "PL_FAKE_FIXTURE"}},
        }]})

    def playlistItems(self):
        return FakeResource({"items": [{"contentDetails": {"videoId": "VID_FAKE_FIXTURE"}}]})

    def videos(self):
        return FakeResource({"items": [{
            "snippet": {"title": "FAKE_FIXTURE skincare routine", "description": "", "tags": ["skincare"], "publishedAt": "2026-09-01T00:00:00Z"},
            "statistics": {"viewCount": "1000", "likeCount": "40", "commentCount": "10"},
        }]})


def test_enrichment_extracts_public_fields_and_metrics(tmp_path):
    paths = {
        "cache_dir": str(tmp_path / "cache"),
        "raw_channels": str(tmp_path / "raw_channels.csv"),
        "influencers": str(tmp_path / "influencers.csv"),
        "log_file": str(tmp_path / "pipeline.log"),
    }
    pd.DataFrame([{
        "channel_id": "UC_FAKE_FIXTURE", "title": "FAKE_FIXTURE Creator",
        "source_keyword": "skincare", "fetched_at": "2026-10-01T00:00:00+00:00",
    }]).to_csv(paths["raw_channels"], index=False)
    config = {"paths": paths, "enrichment": {"recent_videos": 10}, "filtering": {"niche_keywords": ["skincare", "beauty"]}}

    rows = enrich_channels(config, FakeYouTube())
    assert rows[0]["email"] == "hello@creator.test"
    assert rows[0]["instagram_url"] == "https://instagram.com/creator"
    assert rows[0]["website"] == "https://brand.test/contact"
    assert rows[0]["followers"] == 20000
    assert rows[0]["engagement_rate"] == 0.05
    assert rows[0]["language"] == "en"
    assert (tmp_path / "influencers.csv").exists()


def test_personalizer_uses_groq_json_chat_completion():
    email_text = " ".join(["FAKE_FIXTURE"] * 60)
    dm_text = " ".join(["FAKE_FIXTURE"] * 15)
    payload = json.dumps({"subject": "FAKE_FIXTURE collaboration", "email": email_text, "dm": dm_text})

    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    config = {
        "personalization": {
            "email_words": [60, 90], "dm_words": [15, 30], "max_retries": 3,
            "model": "FAKE_FIXTURE", "max_tokens": 500, "temperature": 0.2,
            "delay_between_requests_seconds": 0,
        },
        "brand": {"name": "FAKE_FIXTURE Brand", "product": "FAKE_FIXTURE product", "value_prop": "FAKE_FIXTURE value"},
        "collaboration": {
            "high_engagement_rate": 0.04, "mid_engagement_rate": 0.02,
            "high_reach_followers": 50000, "high_reach_views": 10000,
            "high_engagement_angle": "UGC", "mid_engagement_angle": "affiliate",
            "high_reach_angle": "paid", "default_angle": "seeding",
        },
    }
    row = {"id": "FAKE_FIXTURE", "name": "FAKE_FIXTURE Creator", "email": "Not Found", "engagement_rate": 0.05}
    client = FakeClient()
    result = _personalize_one(row, config, client, ("system JSON", "{name} {collab_angle} JSON", "{email_words} {dm_words}"))
    assert result["message_status"] == "PENDING_APPROVAL"
    assert result["approved"] is False
    assert result["collab_angle"] == "UGC"
    request = client.chat.completions.kwargs
    assert request["model"] == "FAKE_FIXTURE"
    assert request["max_tokens"] == 500
    assert request["temperature"] == 0.2
    assert request["response_format"] == {"type": "json_object"}
    assert request["messages"] == [
        {"role": "system", "content": "system JSON"},
        {"role": "user", "content": "FAKE_FIXTURE Creator UGC JSON"},
    ]


def _install_fake_groq(monkeypatch):
    module = ModuleType("groq")

    class APIStatusError(Exception):
        def __init__(self, message="api error", status_code=500, headers=None):
            super().__init__(message)
            self.status_code = status_code
            self.response = SimpleNamespace(headers=headers or {})

    class RateLimitError(APIStatusError):
        def __init__(self, message="rate limited", headers=None):
            super().__init__(message, 429, headers)

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class InternalServerError(Exception):
        pass

    class BadRequestError(APIStatusError):
        pass

    class AuthenticationError(APIStatusError):
        pass

    class PermissionDeniedError(APIStatusError):
        pass

    for error_type in (
        APIStatusError, RateLimitError, APIConnectionError, APITimeoutError,
        InternalServerError, BadRequestError, AuthenticationError, PermissionDeniedError,
    ):
        setattr(module, error_type.__name__, error_type)
    monkeypatch.setitem(sys.modules, "groq", module)
    return module


def test_groq_retry_after_and_authentication_error(monkeypatch):
    fake_groq = _install_fake_groq(monkeypatch)
    delays = []
    monkeypatch.setattr("src.utils.retry.time.sleep", delays.append)

    class FlakyClient:
        def __init__(self):
            self.calls = 0

        class chat:
            pass

    client = FlakyClient()
    completions = SimpleNamespace()

    def create(**kwargs):
        client.calls += 1
        if client.calls == 1:
            raise fake_groq.RateLimitError(headers={"retry-after": "0.25"})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    completions.create = create
    client.chat = SimpleNamespace(completions=completions)
    assert _request_message(client, "model", "system", "user JSON", 100, 0.1) == "{}"
    assert delays == [0.25]
    assert client.calls == 2

    class UnauthorizedClient:
        def __init__(self):
            self.calls = 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            self.calls += 1
            raise fake_groq.AuthenticationError("invalid key", status_code=401)

    unauthorized = UnauthorizedClient()
    with pytest.raises(fake_groq.AuthenticationError):
        _request_message(unauthorized, "model", "system", "user JSON", 100, 0.1)
    assert unauthorized.calls == 1


def test_all_personalization_rows_failed_exits_without_placeholder_csv(tmp_path, monkeypatch, caplog):
    shortlist_path = tmp_path / "shortlist.csv"
    pd.DataFrame([{"id": "FAKE_FIXTURE", "name": "FAKE_FIXTURE", "status": "PASS"}]).to_csv(shortlist_path, index=False)
    output_path = tmp_path / "messages.csv"
    config = {
        "paths": {"shortlist": str(shortlist_path), "messages": str(output_path), "log_file": str(tmp_path / "pipeline.log")},
        "personalization": {"delay_between_requests_seconds": 0},
    }

    def fail_row(*args):
        raise ValueError("FAKE_FIXTURE generation failure")

    monkeypatch.setattr("src.personalize._personalize_one", fail_row)
    with pytest.raises(SystemExit) as error:
        personalize_messages(config, client=object())
    assert error.value.code == 1
    assert not output_path.exists()
    assert any("Generated 0/1 drafts (1 failed)" in record.message for record in caplog.records)


def test_fatal_groq_error_aborts_personalization_immediately(tmp_path, monkeypatch):
    fake_groq = _install_fake_groq(monkeypatch)
    shortlist_path = tmp_path / "shortlist.csv"
    pd.DataFrame([
        {"id": "FAKE_FIXTURE_1", "name": "FAKE_FIXTURE_1", "status": "PASS"},
        {"id": "FAKE_FIXTURE_2", "name": "FAKE_FIXTURE_2", "status": "PASS"},
    ]).to_csv(shortlist_path, index=False)
    output_path = tmp_path / "messages.csv"
    config = {
        "paths": {"shortlist": str(shortlist_path), "messages": str(output_path), "log_file": str(tmp_path / "pipeline.log")},
        "personalization": {"delay_between_requests_seconds": 0},
    }
    attempts = []

    def unauthorized(*args):
        attempts.append(True)
        raise fake_groq.AuthenticationError("invalid key", status_code=401)

    monkeypatch.setattr("src.personalize._personalize_one", unauthorized)
    with pytest.raises(RuntimeError, match="Fatal Groq API error"):
        personalize_messages(config, client=object())
    assert len(attempts) == 1
    assert not output_path.exists()


def test_personalization_observes_configured_inter_row_delay(tmp_path, monkeypatch):
    shortlist_path = tmp_path / "shortlist.csv"
    pd.DataFrame([
        {"id": "FAKE_FIXTURE_1", "name": "FAKE_FIXTURE_1", "status": "PASS"},
        {"id": "FAKE_FIXTURE_2", "name": "FAKE_FIXTURE_2", "status": "PASS"},
    ]).to_csv(shortlist_path, index=False)
    config = {
        "paths": {"shortlist": str(shortlist_path), "messages": str(tmp_path / "messages.csv"), "log_file": str(tmp_path / "pipeline.log")},
        "personalization": {"delay_between_requests_seconds": 0.25},
    }
    sleeps = []
    monkeypatch.setattr("src.personalize.time.sleep", sleeps.append)
    monkeypatch.setattr("src.personalize._personalize_one", lambda row, *args: {
        "influencer_id": row["id"], "influencer": row["name"], "email": "Not Found",
        "subject": "FAKE_FIXTURE", "email_message": "FAKE_FIXTURE", "dm": "FAKE_FIXTURE",
        "collab_angle": "FAKE_FIXTURE", "message_status": "PENDING_APPROVAL", "approved": False,
    })

    result = personalize_messages(config, client=object())
    assert len(result) == 2
    assert sleeps == [0.25]


def test_sender_dry_run_live_transition_and_email_deduplication(tmp_path, monkeypatch):
    paths = {
        "messages": str(tmp_path / "messages.csv"),
        "outreach_log": str(tmp_path / "outreach_log.csv"),
        "dm_queue": str(tmp_path / "dm_manual_queue.csv"),
        "log_file": str(tmp_path / "pipeline.log"),
    }
    pd.DataFrame([{
        "influencer_id": "FAKE_FIXTURE", "influencer": "FAKE_FIXTURE Creator",
        "email": "creator@example.org", "subject": "FAKE_FIXTURE collaboration",
        "email_message": "FAKE_FIXTURE message", "dm": "FAKE_FIXTURE DM",
        "message_status": "PENDING_APPROVAL", "approved": True,
    }]).to_csv(paths["messages"], index=False)
    config = {"paths": paths, "sending": {"dry_run": False}}

    first = send_outreach(config)
    second = send_outreach(config)
    sent_emails = []
    monkeypatch.setattr("src.sender._send_to_test_inbox", lambda row: sent_emails.append(row["email"]))
    live_attempt = send_outreach(config, live=True)
    live_duplicate = send_outreach(config, live=True)
    queue = pd.read_csv(paths["dm_queue"])
    assert first[0]["status"] == "SIMULATED"
    assert second[0]["status"] == "SKIPPED_DUPLICATE"
    assert live_attempt[0]["status"] == "SENT_TO_TEST_INBOX"
    assert live_duplicate[0]["status"] == "SKIPPED_DUPLICATE"
    assert sent_emails == ["creator@example.org"]
    assert len(queue) == 1
    assert queue.loc[0, "status"] == "PENDING_MANUAL"