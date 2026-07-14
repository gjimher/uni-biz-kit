from pathlib import Path

from .. import dev_ports


_SCRIPT = r'''#!/usr/bin/python3
"""Deterministic OData-like source for integration development and demos.

GET /odata/v4/Accounts supports $top, $skiptoken, $filter=modifiedOn gt ...,
$orderby and $select. POST /mock/reset restores the seed; POST /mock/advance
applies the next deterministic change; GET /mock/state reports the scenario.
GET requests never mutate data, so a paginated snapshot remains predictable.

The command can also control an already-running mock: --advance applies the
next change, --reset restores the seed and --terminate stops it through a
loopback-only endpoint.
"""
import argparse
import json
import re
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlparse

DEFAULT_PORT = __PORT__

SEED = [
    {"accountId":"ES|1001","legalName":"Industrias Norte S.L.","statusCode":1,"modifiedOn":"2026-07-12T08:00:00Z","addresses":[{"addressType":"INVOICE","isPrimary":False,"line1":"Calle Fiscal 1","city":"Bilbao","region":"Bizkaia","country":"ES"},{"addressType":"POSTAL","isPrimary":True,"line1":"Gran Via 10","city":"Bilbao","region":"Bizkaia","country":"ES"}]},
    {"accountId":"ES|1002","legalName":"Servicios Mediterraneo S.A.","statusCode":1,"modifiedOn":"2026-07-12T08:05:00Z","addresses":[{"addressType":"POSTAL","isPrimary":True,"line1":"Carrer Major 20","city":"Valencia","region":"Valencia","country":"ES"}]},
    {"accountId":"PT|2001","legalName":"Comercio Atlantico Lda.","statusCode":1,"modifiedOn":"2026-07-12T08:10:00Z","addresses":[{"addressType":"POSTAL","isPrimary":True,"line1":"Rua do Porto 3","city":"Porto","region":"Porto","country":"PT"}]}
]
CHANGES = [
    {"op":"upsert","record":{"accountId":"ES|1003","legalName":"Nueva Empresa S.A.","statusCode":1,"modifiedOn":"2026-07-12T08:15:00Z","addresses":[{"addressType":"POSTAL","isPrimary":True,"line1":"Alcala 42","city":"Madrid","region":"Madrid","country":"ES"}]}},
    {"op":"update","id":"ES|1001","values":{"legalName":"Industrias Norte Renovada S.L.","modifiedOn":"2026-07-12T08:20:00Z"}},
    {"op":"update","id":"ES|1002","values":{"modifiedOn":"2026-07-12T08:25:00Z","addresses":[{"addressType":"POSTAL","isPrimary":False,"line1":"Carrer Major 20","city":"Valencia","region":"Valencia","country":"ES"},{"addressType":"HEADQUARTERS","isPrimary":True,"line1":"Avinguda Nova 7","city":"Valencia","region":"Valencia","country":"ES"}]}},
    {"op":"delete","id":"PT|2001","modifiedOn":"2026-07-12T08:30:00Z"}
]

records = []
tombstones = []
step = 0

def reset():
    global records, tombstones, step
    records = json.loads(json.dumps(SEED)); tombstones = []; step = 0

def advance():
    global step
    if step < len(CHANGES):
        change = CHANGES[step]
    else:
        number = step - len(CHANGES) + 1
        modified_on = datetime(2026, 7, 12, 8, 30, tzinfo=timezone.utc) + timedelta(minutes=5 * number)
        change = {
            "op": "upsert",
            "record": {
                "accountId": f"DEMO|{3000 + number}",
                "legalName": f"Empresa Demo {number} S.L.",
                "statusCode": 1,
                "modifiedOn": modified_on.isoformat().replace("+00:00", "Z"),
                "addresses": [{
                    "addressType": "POSTAL",
                    "isPrimary": True,
                    "line1": f"Avenida Demo {number}",
                    "city": "Sevilla",
                    "region": "Sevilla",
                    "country": "ES",
                }],
            },
        }
    step += 1
    if change["op"] == "upsert": records.append(change["record"])
    elif change["op"] == "update":
        next(row for row in records if row["accountId"] == change["id"]).update(change["values"])
    else:
        records[:] = [row for row in records if row["accountId"] != change["id"]]
        tombstones.append({"accountId":change["id"],"modifiedOn":change["modifiedOn"],"@removed":{"reason":"deleted"}})
    return True

reset()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print(f"OData mock: {fmt % args}", flush=True)
    def send_json(self, status, body):
        data=json.dumps(body).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        global step
        if self.path == "/mock/reset": reset(); return self.send_json(200,{"step":step,"records":len(records)})
        if self.path == "/mock/advance":
            changed=advance(); return self.send_json(200,{"advanced":changed,"step":step,"records":len(records),"tombstones":len(tombstones)})
        if self.path == "/mock/shutdown":
            peer = self.client_address[0]
            if peer not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
                return self.send_json(403,{"error":"Shutdown is only allowed from loopback"})
            self.send_json(200,{"status":"shutting_down"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self.send_json(404,{"error":"Not found"})
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path == "/mock/state": return self.send_json(200,{"step":step,"remaining":max(0,len(CHANGES)-step),"records":records,"tombstones":tombstones})
        if parsed.path != "/odata/v4/Accounts": return self.send_json(404,{"error":"Not found"})
        query=parse_qs(parsed.query); rows=list(records)+list(tombstones)
        filter_expr=query.get("$filter",[""])[0]
        match=re.search(r"modifiedOn\s+gt\s+(.+)$",filter_expr)
        if match: rows=[row for row in rows if row["modifiedOn"] > match.group(1).strip(" '")]
        rows.sort(key=lambda row:(row["modifiedOn"],row["accountId"]))
        top=max(1,min(int(query.get("$top",[2])[0]),100)); offset=int(query.get("$skiptoken",[0])[0]); page=rows[offset:offset+top]
        selected=query.get("$select",[""])[0].split(",") if query.get("$select") else []
        if selected: page=[{key:row.get(key) for key in selected} | ({"@removed":row["@removed"]} if "@removed" in row else {}) for row in page]
        body={"@odata.context":"$metadata#Accounts","value":page}
        if offset+len(page)<len(rows):
            params={k:v[-1] for k,v in query.items()}; params["$skiptoken"]=str(offset+len(page)); body["@odata.nextLink"]=f"http://localhost:{self.server.server_port}/odata/v4/Accounts?{urlencode(params)}"
        else: body["@odata.deltaLink"]=f"http://localhost:{self.server.server_port}/odata/v4/Accounts?$deltatoken={step}"
        self.send_json(200,body)

def call_action(port, action, *, missing_ok=False):
    request=urllib.request.Request(f"http://127.0.0.1:{port}/mock/{action}",data=b"{}",headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(request,timeout=5) as response:
            body=json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        detail=error.read().decode(errors="replace")
        raise SystemExit(f"Port {port} is not controlled by this OData mock: HTTP {error.code} {detail}")
    except urllib.error.URLError as error:
        if missing_ok:
            print(json.dumps({"status":"not_running","port":port},sort_keys=True)); return
        raise SystemExit(f"OData mock is not reachable on port {port}: {error}")
    print(json.dumps(body,sort_keys=True))
    if action == "shutdown":
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                try: probe.bind(("0.0.0.0",port)); return
                except OSError: time.sleep(0.1)
        raise SystemExit(f"OData mock did not release port {port}")

def main():
    parser=argparse.ArgumentParser(
        description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  %(prog)s\n  %(prog)s --terminate\n  %(prog)s --reset\n  %(prog)s --advance",
    )
    parser.add_argument("port",nargs="?",type=int,default=DEFAULT_PORT,help=f"HTTP port (default: {DEFAULT_PORT})")
    actions=parser.add_mutually_exclusive_group()
    actions.add_argument("--terminate",action="store_true",help="stop a running mock on this port and exit")
    actions.add_argument("--advance",action="store_true",help="apply the next deterministic change and exit")
    actions.add_argument("--reset",action="store_true",help="restore the seed scenario and exit")
    args=parser.parse_args()
    if args.terminate: return call_action(args.port,"shutdown",missing_ok=True)
    if args.advance: return call_action(args.port,"advance")
    if args.reset: return call_action(args.port,"reset")
    server=ThreadingHTTPServer(("0.0.0.0",args.port),Handler); print(f"Integration OData mock listening on http://localhost:{args.port}",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__": main()
'''


def generate(bin_dir: Path):
    path = bin_dir / "dev-integration-odata-mock.py"
    path.write_text(_SCRIPT.replace("__PORT__", str(dev_ports.INTEGRATION_MOCK)), encoding="utf-8")
    path.chmod(0o755)
