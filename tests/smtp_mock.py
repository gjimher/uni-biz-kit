"""
Shared in-process SMTP mock server for user-management E2E tests.

Usage:
    # In conftest.py the smtp_server fixture starts/stops the server.
    # Test files import the globals to read captured emails.
    from smtp_mock import smtp_emails, smtp_lock, extract_links, SMTP_PORT
"""

import os
import re
import threading

_env_num = int(os.environ.get('UBK_DEV_ENV_NUM', '0'))
SMTP_PORT = 3000 + 100 * _env_num + 10

smtp_emails: list[dict] = []
smtp_lock = threading.Lock()


class MockSMTPHandler:
    """aiosmtpd handler that appends every received message to smtp_emails."""

    async def handle_DATA(self, server, session, envelope):
        with smtp_lock:
            smtp_emails.append({
                "mail_from": envelope.mail_from,
                "rcpt_tos": envelope.rcpt_tos,
                "content": envelope.content.decode("utf-8", errors="replace"),
            })
        return "250 Message accepted for delivery"


def extract_links(text: str) -> list[str]:
    """Return all http(s) URLs found in a (possibly quoted-printable) email body."""
    import quopri
    import html as _html
    decoded = quopri.decodestring(text.encode("utf-8", errors="replace")).decode("utf-8", errors="replace")
    unescaped = _html.unescape(decoded)
    raw = re.findall(r"https?://[^\s<>\"']+", unescaped)
    return [l.replace("=\n", "").replace("=\r\n", "").replace("\n", "").replace("\r", "") for l in raw]
