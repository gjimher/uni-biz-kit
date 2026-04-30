from pathlib import Path

_SCRIPT = r'''#!/usr/bin/python3
"""Development SMTP mock server — captures emails and prints them to stdout."""

import asyncio
import html
import os
import quopri
import re
import sys
from datetime import datetime

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("SMTP_MOCK_PORT", 3000 + 100 * int(os.environ.get("UBK_DEV_ENV_NUM", "0")) + 10))


def extract_links(body: str) -> list:
    decoded = body
    if re.search(r'Content-Transfer-Encoding:\s*quoted-printable', body, re.IGNORECASE):
        parts = re.split(r'\n\n', body, maxsplit=1)
        if len(parts) == 2:
            headers, content = parts
            try:
                decoded = headers + '\n\n' + quopri.decodestring(content.encode()).decode('utf-8', errors='replace')
            except Exception:
                pass
    return re.compile(r'https?://[^\s<>"\']+').findall(html.unescape(decoded))


class SMTPSession:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.mail_from = ""
        self.rcpt_to = []
        self.data_lines = []
        self.in_data = False

    async def send(self, line):
        self.writer.write((line + "\r\n").encode())
        await self.writer.drain()

    async def handle(self):
        await self.send("220 localhost SMTP Mock")
        try:
            while True:
                raw = await asyncio.wait_for(self.reader.readline(), timeout=60)
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip("\r\n")
                if self.in_data:
                    if line == ".":
                        self.in_data = False
                        await self._print_email()
                        await self.send("250 OK: Message accepted")
                    else:
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
        except (asyncio.TimeoutError, ConnectionResetError):
            pass
        finally:
            self.writer.close()

    async def _print_email(self):
        body = "\n".join(self.data_lines)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sep = "=" * 72
        output = f"\n{sep}\nSMTP EMAIL RECEIVED at {timestamp}\n{sep}\nFROM:    {self.mail_from}\nTO:      {', '.join(self.rcpt_to)}\n{sep}\n{body}"
        links = extract_links(body)
        if links:
            output += "\n--- LINKS FOUND ---\n" + "".join(f"  {lnk}\n" for lnk in links)
        output += sep
        print(output, flush=True)


async def handle_client(reader, writer):
    await SMTPSession(reader, writer).handle()


async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", PORT)
    print(f"\n{'=' * 60}\n  Dev SMTP Mock — listening on port {PORT}\n{'=' * 60}\n", flush=True)
    async with server:
        await server.serve_forever()


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\nSMTP mock server stopped.")
'''


def generate(bin_dir: Path):
    script = bin_dir / "dev-smtp-mock.py"
    script.write_text(_SCRIPT)
    script.chmod(0o755)
