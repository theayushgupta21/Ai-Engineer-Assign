"""Retry helpers with exponential backoff and provider-aware error handling."""
import functools
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Callable, Type

from src.utils.logger import get_logger

log = get_logger(__name__)


def is_groq_transient_error(error: Exception) -> bool:
    """Return whether a Groq exception is safe to retry."""
    try:
        from groq import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
    except ImportError:
        return False
    return isinstance(
        error, (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
    ) or is_groq_row_error(error)


def is_groq_fatal_error(error: Exception) -> bool:
    if is_groq_row_error(error):
        return False
    import groq
    fatal_types = tuple(
        getattr(groq, name)
        for name in ("AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError")
        if hasattr(groq, name)
    )
    status = getattr(error, "status_code", None)
    return isinstance(error, fatal_types) or status in (400, 401, 402, 403, 404)

    # Per-row output problems: skip that row, don't abort the whole stage.
    if is_groq_row_error(error):
        return False

    if isinstance(error, (AuthenticationError, PermissionDeniedError, NotFoundError, BadRequestError)):
        return True
    return isinstance(error, APIStatusError) and getattr(error, "status_code", None) in (400, 401, 402, 403, 404)


def is_groq_row_error(error: Exception) -> bool:
    """400s caused by one bad generation (e.g. invalid JSON), not by config or account."""
    return getattr(error, "status_code", None) == 400 and "json_validate_failed" in str(error)

def retry(max_attempts: int = 3, base_delay: float = 1.0,
          exceptions: tuple[Type[Exception], ...] = (Exception,),
          retry_if: Callable[[Exception], bool] | None = None) -> Callable:
    """Retry a function on failure; re-raise after the last attempt."""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if not isinstance(e, exceptions) or (retry_if is not None and not retry_if(e)):
                        raise
                    if attempt == max_attempts:
                        log.error("%s failed after %d attempts: %s", fn.__name__, attempt, e)
                        raise
                    delay = _retry_delay(e, base_delay, attempt)
                    log.warning("%s attempt %d failed (%s); retrying in %.1fs",
                                fn.__name__, attempt, e, delay)
                    time.sleep(delay)
        return wrapper
    return deco


def _retry_delay(error: Exception, base_delay: float, attempt: int) -> float:
    """Use a Groq 429 retry-after header when supplied, else exponential backoff."""
    if getattr(error, "status_code", None) == 429:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", {}) or {}
        value = headers.get("retry-after") or headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                try:
                    retry_at = parsedate_to_datetime(value)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
    return base_delay * (2 ** (attempt - 1))
