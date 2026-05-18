"""Email sending via Mailgun REST API using urllib only."""

import base64
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _make_auth_header(api_key: str) -> str:
    """Return the Basic auth header value for a Mailgun API key."""
    encoded = base64.b64encode(f"api:{api_key}".encode()).decode()
    return f"Basic {encoded}"


def _multipart_body(fields: list[tuple[str, str]], files: list[dict]) -> tuple[bytes, str]:
    """
    Build a multipart/form-data body.

    fields: list of (name, value) string pairs
    files:  list of dicts with keys: name, filename, content_type, data (bytes)

    Returns (body_bytes, content_type_header_value).
    """
    boundary = "------ServerReportBoundary7f3a2b"
    parts = []
    crlf = b"\r\n"

    for name, value in fields:
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n'
            f"\r\n"
            f"{value}\r\n".encode()
        )

    for f in files:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{f["name"]}"; '
            f'filename="{f["filename"]}"\r\n'
            f'Content-Type: {f["content_type"]}\r\n'
            f"\r\n"
        ).encode()
        parts.append(header + f["data"] + crlf)

    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def send_body(
    *,
    api_url: str,
    api_key: str,
    from_addr: str,
    to: str,
    subject: str,
    body_text: str | None = None,
    body_html: str | None = None,
) -> None:
    """
    Send an email with a text and/or HTML body via Mailgun.

    At least one of body_text or body_html must be provided.
    """
    fields = [
        ("from", from_addr),
        ("to", to),
        ("subject", subject),
    ]
    if body_text is not None:
        fields.append(("text", body_text))
    if body_html is not None:
        fields.append(("html", body_html))

    data = urllib.parse.urlencode(fields).encode("utf-8")
    _post(api_url, api_key, data, "application/x-www-form-urlencoded")


def send_attachment(
    *,
    api_url: str,
    api_key: str,
    from_addr: str,
    to: str,
    subject: str,
    plain_body: str,
    filename: str,
    content: str,
) -> None:
    """
    Send an email with a plain text body and a single file attachment via Mailgun.
    """
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    fields = [
        ("from", from_addr),
        ("to", to),
        ("subject", subject),
        ("text", plain_body),
    ]
    files = [
        {
            "name": "attachment",
            "filename": filename,
            "content_type": content_type,
            "data": content.encode("utf-8"),
        }
    ]
    body, ct = _multipart_body(fields, files)
    _post(api_url, api_key, body, ct)


def _post(url: str, api_key: str, data: bytes, content_type: str) -> None:
    """POST data to the Mailgun API and raise RuntimeError on failure."""
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", _make_auth_header(api_key))
    req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 201):
                body = resp.read().decode("utf-8")
                raise RuntimeError(f"Mailgun returned HTTP {resp.status}: {body}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection error: {e.reason}") from e


def dispatch(
    results: Any,
    hostname: str,
    timestamp: str,
    version: str,
    config: dict,
    rendered: dict[str, str],
) -> None:
    """
    Send the report to all configured recipients.

    rendered: mapping of format name -> rendered string, pre-computed by main.py.
    config: the merged general config dict.
    """
    api_key = os.environ.get("MAILGUN_API_KEY", "")
    domain = config.get("mailgun_domain", "")
    api_base = config.get("mailgun_api_url", "https://api.mailgun.net/v3")
    from_addr = config.get("email_from", f"server-report@{domain}")
    api_url = f"{api_base}/{domain}/messages"

    subject = f"[Server Report] {hostname} — {timestamp}"

    for recipient in config.get("recipients", []):
        to = recipient["email"]
        fmt = recipient.get("format", "text")
        content = rendered.get(fmt, "")
        if not content:
            continue

        if fmt == "text":
            send_body(
                api_url=api_url, api_key=api_key,
                from_addr=from_addr, to=to, subject=subject,
                body_text=content,
            )
        elif fmt == "html":
            send_body(
                api_url=api_url, api_key=api_key,
                from_addr=from_addr, to=to, subject=subject,
                body_html=content,
            )
        elif fmt in ("json", "csv"):
            from formatters.json import JsonFormatter
            from formatters.csv import CsvFormatter
            ext = ".json" if fmt == "json" else ".csv"
            filename = f"server-report-{hostname}-{timestamp.replace(':', '-').replace(' ', '_')}{ext}"
            plain_body = f"Server report for {hostname} - {timestamp}"
            send_attachment(
                api_url=api_url, api_key=api_key,
                from_addr=from_addr, to=to, subject=subject,
                plain_body=plain_body,
                filename=filename,
                content=content,
            )
