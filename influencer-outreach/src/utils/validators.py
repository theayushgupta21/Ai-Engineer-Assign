"""Validation helpers: emails (extract only, never guess), word counts."""
import re

NOT_FOUND = "Not Found"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_BAD_DOMAINS = {"example.com", "domain.com", "email.com"}


def is_valid_email(value: str | None) -> bool:
    """True only for a syntactically valid email (not the 'Not Found' marker)."""
    if not value or value == NOT_FOUND:
        return False
    m = _EMAIL_RE.fullmatch(value.strip())
    return bool(m) and value.split("@")[-1].lower() not in _BAD_DOMAINS


def extract_email(text: str | None) -> str:
    """Return the first real email found in public text, else 'Not Found'. Never guesses."""
    if not text:
        return NOT_FOUND
    for cand in _EMAIL_RE.findall(text):
        cand = cand.strip(".,;:")
        if is_valid_email(cand):
            return cand.lower()
    return NOT_FOUND


def word_count(text: str) -> int:
    return len(text.split())


def within_words(text: str, bounds: tuple[int, int]) -> bool:
    lo, hi = bounds
    return lo <= word_count(text) <= hi
