# websearch

A Python project.

## Configuration

Environment variables (empty and unset read identically):

| Variable | Purpose |
| --- | --- |
| `HTTPS_PROXY` | Optional egress proxy for the shared HTTP client. The value's scheme selects the protocol: `http://`, `socks5://` (local DNS), or `socks5h://` (DNS through the proxy). Unparseable values degrade to direct egress; a `socks5://`/`socks5h://` value requires the `httpx[socks]` extra and fails loudly at startup without it. |
| `WEB_SEARCH_BASE`, `WEB_SEARCH_API_KEY`, `WEB_SEARCH_MODEL` | Cloud search API (Linkup-style). |
| `WEB_FETCH_BASE`, `WEB_FETCH_API_KEY`, `WEB_FETCH_MODEL` | Cloud fetch API. |
