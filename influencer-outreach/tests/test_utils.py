import pytest
from src.utils.validators import extract_email, is_valid_email, within_words, NOT_FOUND
from src.utils.retry import retry
from src.utils.cache import JsonCache


def test_extract_email_found():
    assert extract_email("Business: Hello@Brand.com.") == "hello@brand.com"

def test_extract_email_not_found_never_guesses():
    assert extract_email("no contact here") == NOT_FOUND
    assert extract_email(None) == NOT_FOUND

def test_invalid_email():
    assert not is_valid_email("Not Found")
    assert not is_valid_email("a@example.com")
    assert is_valid_email("a@brand.co")

def test_word_bounds():
    assert within_words("one two three", (3, 5))
    assert not within_words("one two", (3, 5))

def test_retry_then_success():
    calls = {"n": 0}
    @retry(max_attempts=3, base_delay=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"
    assert flaky() == "ok" and calls["n"] == 3

def test_retry_gives_up():
    @retry(max_attempts=2, base_delay=0)
    def bad():
        raise ValueError("x")
    with pytest.raises(ValueError):
        bad()

def test_cache(tmp_path):
    c = JsonCache(str(tmp_path))
    n = {"c": 0}
    def fetch():
        n["c"] += 1
        return {"a": 1}
    assert c.get_or_fetch("k", fetch) == {"a": 1}
    assert c.get_or_fetch("k", fetch) == {"a": 1}
    assert n["c"] == 1
