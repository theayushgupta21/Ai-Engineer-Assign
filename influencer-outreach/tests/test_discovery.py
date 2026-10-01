from src.discovery import discover_channels


class FakeRequest:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeSearch:
    def __init__(self, responses, calls):
        self.responses = responses
        self.calls = calls

    def list(self, **params):
        self.calls.append(params)
        key = (params["type"], params.get("pageToken"))
        return FakeRequest(self.responses[key])


class FakeYouTube:
    def __init__(self, responses):
        self.calls = []
        self.search_api = FakeSearch(responses, self.calls)

    def search(self):
        return self.search_api


def test_discovery_paginates_deduplicates_and_caches(tmp_path):
    responses = {
        ("channel", None): {
            "items": [{"id": {"channelId": "UC1"}, "snippet": {"title": "One"}}],
            "nextPageToken": "next",
        },
        ("channel", "next"): {
            "items": [{"id": {"channelId": "UC2"}, "snippet": {"title": "Two"}}],
        },
        ("video", None): {
            "items": [
                {"id": {"videoId": "V1"}, "snippet": {"channelId": "UC1", "channelTitle": "One"}},
                {"id": {"videoId": "V2"}, "snippet": {"channelId": "UC3", "channelTitle": "Three"}},
            ],
        },
    }
    service = FakeYouTube(responses)
    config = {
        "discovery": {
            "keywords": ["fashion"],
            "max_results_per_keyword": 50,
            "target_raw_channels": 3,
            "region_code": "IN",
            "relevance_language": "en",
        },
        "paths": {
            "cache_dir": str(tmp_path / "cache"),
            "raw_channels": str(tmp_path / "raw_channels.csv"),
            "log_file": str(tmp_path / "pipeline.log"),
        },
    }

    channels = discover_channels(config, service)
    assert [channel["channel_id"] for channel in channels] == ["UC1", "UC2", "UC3"]
    assert channels[2]["title"] == "Three"
    assert [call["type"] for call in service.calls] == ["channel", "channel", "video"]
    assert service.calls[1]["pageToken"] == "next"
    assert (tmp_path / "raw_channels.csv").exists()

    discover_channels(config, service)
    assert len(service.calls) == 3