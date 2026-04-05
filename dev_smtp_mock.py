#!/usr/bin/env python
"""
Development SMTP Mock Server

Listens on a configurable port (default: 3010) and captures all incoming emails.
Prints email content to stdout and appends to tmp-dev-smtp-mock.txt.

Usage:
    python dev_smtp_mock.py [port]
    python dev_smtp_mock.py 3010

Environment:
    SMTP_MOCK_PORT  - Port to listen on (default: 3010)
    SMTP_MOCK_LOG   - Log file path (default: tmp-dev-smtp-mock.txt)
"""

import asyncio
import sys
import os
import re
import quopri
import html
from datetime import datetime

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("SMTP_MOCK_PORT", 3010))
LOG_FILE = os.environ.get("SMTP_MOCK_LOG", "tmp-dev-smtp-mock.txt")


def log(text: str):
    """Write to stdout and to the log file."""
    print(text)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def extract_links(body: str) -> list:
    """Extract all URLs from the email body, decoding quoted-printable and HTML entities."""
    decoded_body = body
    if re.search(r'Content-Transfer-Encoding:\s*quoted-printable', body, re.IGNORECASE):
        parts = re.split(r'\n\n', body, maxsplit=1)
        if len(parts) == 2:
            headers, content = parts
            try:
                decoded_content = quopri.decodestring(content.encode()).decode('utf-8', errors='replace')
                decoded_body = headers + '\n\n' + decoded_content
            except Exception:
                pass
    decoded_body = html.unescape(decoded_body)
    url_pattern = re.compile(r'https?://[^\s<>"\']+')
    return url_pattern.findall(decoded_body)


class SMTPSession:
    """Handles a single SMTP client connection."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.mail_from = ""
        self.rcpt_to = []
        self.data_lines = []
        self.in_data = False
        self.peer = writer.get_extra_info("peername", ("?", 0))

    async def send(self, line: str):
        self.writer.write((line + "\r\n").encode())
        await self.writer.drain()

    async def handle(self):
        await self.send("220 localhost UniBizKit SMTP Mock Server")

        try:
            while True:
                raw = await asyncio.wait_for(self.reader.readline(), timeout=60)
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip("\r\n")

                if self.in_data:
                    if line == ".":
                        self.in_data = False
                        await self._save_email()
                        await self.send("250 OK: Message accepted")
                    else:
                        # Unescape leading dots
                        self.data_lines.append(line[1:] if line.startswith("..") else line)
                    continue

                cmd = line.upper()

                if cmd.startswith("EHLO") or cmd.startswith("HELO"):
                    await self.send("250-localhost\r\n250-SIZE 10240000\r\n250 OK")
                elif cmd.startswith("MAIL FROM:"):
                    self.mail_from = re.sub(r".*<(.+)>.*", r"\1", line[10:].strip()) or line[10:].strip()
                    await self.send("250 OK")
                elif cmd.startswith("RCPT TO:"):
                    rcpt = re.sub(r".*<(.+)>.*", r"\1", line[8:].strip()) or line[8:].strip()
                    self.rcpt_to.append(rcpt)
                    await self.send("250 OK")
                elif cmd == "DATA":
                    await self.send("354 End data with <CR><LF>.<CR><LF>")
                    self.data_lines = []
                    self.in_data = True
                elif cmd == "QUIT":
                    await self.send("221 Bye")
                    break
                elif cmd == "RSET":
                    self.mail_from = ""
                    self.rcpt_to = []
                    self.data_lines = []
                    await self.send("250 OK")
                elif cmd.startswith("AUTH"):
                    await self.send("235 Authentication successful")
                elif cmd == "NOOP":
                    await self.send("250 OK")
                else:
                    await self.send("500 Command not recognized")
        except asyncio.TimeoutError:
            pass
        except ConnectionResetError:
            pass
        finally:
            self.writer.close()

    async def _save_email(self):
        body = "\n".join(self.data_lines)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        links = extract_links(body)

        separator = "=" * 72
        output = f"""
{separator}
SMTP EMAIL RECEIVED at {timestamp}
{separator}
FROM:    {self.mail_from}
TO:      {", ".join(self.rcpt_to)}
{separator}
{body}
"""
        if links:
            output += f"\n--- LINKS FOUND ---\n"
            for link in links:
                output += f"  {link}\n"
        output += separator

        log(output)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    session = SMTPSession(reader, writer)
    await session.handle()


async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", PORT)
    banner = f"""
{"=" * 60}
  UniBizKit Dev SMTP Mock Server
  Listening on port {PORT}
  Logging to: {LOG_FILE}
{"=" * 60}
"""
    log(banner)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSMTP mock server stopped.")
