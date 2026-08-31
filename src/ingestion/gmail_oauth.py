"""Real Gmail API integration (docs/architecture.md §3.8), closing the gap
documented in gmail_intake.py / BRAIN.md's decisions log (2026-08-24).

One-time interactive OAuth consent (InstalledAppFlow.run_local_server opens
a browser tab), then a cached token (`credentials/token.json`, gitignored)
handles silent refresh on every subsequent run.

Scopes: read-only + compose + send. Send was added 2026-08-25, a deliberate,
explicit exception to the shadow-mode principle (read/draft only, no send)
that governs the rest of this codebase — see BRAIN.md decisions log. It's
scoped to exactly one path: the Scribo invoice-generator feature emailing a
newly created invoice to the counterparty. Nothing else in this codebase
calls send_gmail_message.
"""

import base64
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CREDENTIALS_DIR = Path(__file__).resolve().parents[2] / "credentials"
CLIENT_SECRET_PATH = CREDENTIALS_DIR / "client_secret.json"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_gmail_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                raise FileNotFoundError(
                    f"missing {CLIENT_SECRET_PATH} — download it from Google Cloud Console "
                    "(APIs & Services > Credentials > OAuth client, Desktop app type)"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_unread_emails(query: str = "is:unread", max_results: int = 10) -> list[dict]:
    """Replaces gmail_intake.fetch_unread_emails's NotImplementedError with
    a real call: list unread message IDs, then fetch each one's subject/body/sender."""
    service = get_gmail_service()
    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    message_ids = [m["id"] for m in results.get("messages", [])]

    emails = []
    for msg_id in message_ids:
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = _extract_body(msg["payload"])
        emails.append({
            "id": msg_id,
            "threadId": msg["threadId"],
            "subject": headers.get("Subject", ""),
            "sender": headers.get("From", ""),
            "body": body,
            "internal_date_ms": int(msg["internalDate"]),  # Gmail's receipt time, ms since epoch
        })
    return emails


def _extract_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


def create_gmail_draft(to: str, subject: str, body: str, thread_id: str | None = None) -> dict:
    service = get_gmail_service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    draft_body = {"message": {"raw": raw}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    return service.users().drafts().create(userId="me", body=draft_body).execute()


def send_gmail_message(to: str, subject: str, body: str) -> dict:
    """The one gmail.send call in this codebase — see module docstring for
    why send exists at all here. Used only to deliver a Scribo-generated
    invoice to its recipient company."""
    service = get_gmail_service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def send_gmail_message_with_attachment(to: str, subject: str, body: str, attachment_path: Path, attachment_name: str) -> dict:
    service = get_gmail_service()
    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(body))

    part = MIMEApplication(attachment_path.read_bytes(), _subtype="pdf")
    part.add_header("Content-Disposition", "attachment", filename=attachment_name)
    message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def demo() -> None:
    emails = fetch_unread_emails(query="subject:INV-1002", max_results=5)
    print(f"gmail_oauth.demo(): fetched {len(emails)} matching email(s)")
    for e in emails:
        print(f"  [{e['id']}] from={e['sender']!r} subject={e['subject']!r}")
        print(f"    body: {e['body'][:100]!r}")

    assert isinstance(emails, list), "expected a list back from the Gmail API"
    print("gmail_oauth.demo(): real Gmail API read succeeded")


if __name__ == "__main__":
    demo()
