"""Send approved email drafts safely and maintain a manual DM queue."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import get_secret, load_config
from src.utils.logger import get_logger
from src.utils.retry import retry
from src.utils.validators import NOT_FOUND, is_valid_email

LOG_COLUMNS = ["influencer_id", "influencer", "email", "message_generated", "email_subject", "sent", "date", "status", "error"]
DM_COLUMNS = ["influencer_id", "influencer", "dm", "status"]


def send_outreach(config: dict[str, Any] | None = None, live: bool = False) -> list[dict[str, Any]]:
    """Process approved drafts, deduplicate email, and refresh the manual DM queue."""
    cfg = config or load_config()
    paths = cfg["paths"]
    logger = get_logger(__name__, paths["log_file"])
    messages = _read_csv(paths["messages"])
    existing_log = _read_csv(paths["outreach_log"], LOG_COLUMNS)
    queue = _read_csv(paths["dm_queue"], DM_COLUMNS)
    known_emails = {
        str(row["email"]).strip().lower()
        for row in existing_log.to_dict("records")
        if row.get("email") and not (
            live and row.get("status") in ("SIMULATED", "SKIPPED_DUPLICATE")
        )
    }
    known_dm_ids = {str(value) for value in queue.get("influencer_id", [])}
    dm_rows = queue.to_dict("records")
    attempts = []
    dry_run = not live

    for row in messages.to_dict("records"):
        _queue_dm(row, dm_rows, known_dm_ids)
        if not _approved(row) or not is_valid_email(str(row.get("email", ""))):
            continue
        email = str(row["email"]).strip().lower()
        if email in known_emails:
            attempts.append(_log_row(row, "SKIPPED_DUPLICATE", "", False))
            continue
        try:
            if dry_run:
                status, error = "SIMULATED", ""
            else:
                _send_to_test_inbox(row)
                status, error = "SENT_TO_TEST_INBOX", ""
        except Exception as exc:
            status, error = "FAILED", str(exc)
            logger.exception("Email attempt failed for %s: %s", row.get("influencer_id"), exc)
        attempt = _log_row(row, status, error, not dry_run and status.startswith("SENT"))
        attempts.append(attempt)
        known_emails.add(email)

    _write_rows(paths["outreach_log"], LOG_COLUMNS, existing_log.to_dict("records") + attempts)
    _write_rows(paths["dm_queue"], DM_COLUMNS, dm_rows)
    logger.info("Processed %d approved email attempts; dry_run=%s", len(attempts), dry_run)
    return attempts


def _read_csv(path: str, columns: list[str] | None = None) -> pd.DataFrame:
    """Read a CSV when present, otherwise return an empty frame with headers."""
    file_path = Path(path)
    if file_path.exists():
        return pd.read_csv(file_path).fillna("")
    return pd.DataFrame(columns=columns or [])


def _write_rows(path: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    """Write rows with stable CSV columns, creating parent folders as needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(file_path, index=False)


def _approved(row: dict[str, Any]) -> bool:
    """Require an explicit manual approval and a valid generated draft state."""
    return str(row.get("approved", "")).strip().lower() in ("true", "1", "yes") and row.get("message_status") == "PENDING_APPROVAL"


def _queue_dm(row: dict[str, Any], queue: list[dict[str, Any]], known_ids: set[str]) -> None:
    """Add each generated DM once for manual sending, never auto-send it."""
    influencer_id = str(row.get("influencer_id", ""))
    dm = str(row.get("dm", "")).strip()
    if influencer_id and dm and influencer_id not in known_ids:
        queue.append({"influencer_id": influencer_id, "influencer": row.get("influencer", ""), "dm": dm, "status": "PENDING_MANUAL"})
        known_ids.add(influencer_id)


def _log_row(row: dict[str, Any], status: str, error: str, sent: bool) -> dict[str, Any]:
    """Build one outreach tracker entry with an ISO timestamp."""
    from datetime import datetime, timezone

    return {
        "influencer_id": row.get("influencer_id", ""), "influencer": row.get("influencer", ""),
        "email": row.get("email", NOT_FOUND),
        "message_generated": row.get("email_message", ""), "email_subject": row.get("subject", ""),
        "sent": sent, "date": datetime.now(timezone.utc).isoformat(), "status": status, "error": error,
    }


def _send_to_test_inbox(row: dict[str, Any]) -> None:
    """Send a draft only to the configured test inbox over authenticated SMTP."""
    host = get_secret("SMTP_HOST")
    user = get_secret("SMTP_USER")
    password = get_secret("SMTP_PASSWORD")
    test_inbox = get_secret("TEST_INBOX")
    port = int(get_secret("SMTP_PORT", required=False) or 587)
    message = EmailMessage()
    message["Subject"] = row.get("subject", "")
    message["From"] = user
    message["To"] = test_inbox
    message.set_content(row.get("email_message", ""))
    _smtp_send(host, port, user, password, message)


@retry(max_attempts=3, base_delay=1.0)
def _smtp_send(host: str, port: int, user: str, password: str, message: EmailMessage) -> None:
    """Deliver one message via SMTP with retries for transient errors."""
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(message)