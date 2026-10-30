# websearch

A Python project.

## Configuration

Environment variables (empty and unset read identically):

| Variable | Purpose |
| --- | --- |
| `SOCKS_PROXY` | Optional SOCKS5 egress proxy for the shared HTTP client: `socks5://` (local DNS) or `socks5h://` (DNS through the proxy); unset/empty means direct egress. Requires the `httpx2[socks]` extra. Any other value — HTTP proxies included — fails loudly at startup. |
| `WEB_SEARCH_BASE`, `WEB_SEARCH_API_KEY`, `WEB_SEARCH_MODEL` | Cloud search API (Linkup-style). |
| `WEB_FETCH_BASE`, `WEB_FETCH_API_KEY`, `WEB_FETCH_MODEL` | Cloud fetch API. |
