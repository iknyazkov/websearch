"""One-shot probe of the Go MCP server's stdio protocol shapes.

Sends initialize -> notifications/initialized -> tools/list -> tools/call
(network-free calls only) and dumps every raw response line.
"""

import json
import subprocess
import sys

BIN = sys.argv[1] if len(sys.argv) > 1 else "bin/websearch-go"

proc = subprocess.Popen(
    [BIN],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    bufsize=1,
)


def send(obj: dict) -> None:
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def read() -> dict | None:
    line = proc.stdout.readline()
    if not line:
        return None
    return json.loads(line)


# 1. initialize
send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "judge-probe", "version": "0.0.0"},
}})
print("== initialize ==")
print(json.dumps(read(), indent=2))

# 2. initialized notification
send({"jsonrpc": "2.0", "method": "notifications/initialized"})
import time

time.sleep(0.3)  # drain anything the notification triggers

# 3. tools/list
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
print("== tools/list ==")
resp = read()
print(json.dumps(resp, indent=2))

# 4. tools/call WebSearch with empty query (errors before any network)
send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
    "name": "WebSearch", "arguments": {"query": ""},
}})
print("== tools/call WebSearch empty query ==")
print(json.dumps(read(), indent=2))

# 5. tools/call WebFetch with non-http URL (errors before any network)
send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
    "name": "WebFetch", "arguments": {"url": "ftp://example.com/x"},
}})
print("== tools/call WebFetch ftp url ==")
print(json.dumps(read(), indent=2))

# 6. tools/call unknown tool
send({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
    "name": "Nope", "arguments": {},
}})
print("== tools/call unknown tool ==")
print(json.dumps(read(), indent=2))

# 7. WebSearch with query but no WEB_SEARCH_BASE set -> error path via network attempt
send({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {
    "name": "WebSearch", "arguments": {"query": "test"},
}})
print("== tools/call WebSearch no base ==")
print(json.dumps(read(), indent=2))

proc.terminate()
