# Security Model

Scope: the web platform (`backend/`, `frontend/`) and the audit engine it runs (`skills/`). This describes what is
**implemented and tested**. Items marked *not implemented* are known gaps.

## Threat model

| Actor / input | Risk | Primary controls |
|---|---|---|
| Platform user submitting a URL | SSRF into private networks or cloud metadata; port scanning; abusive load | Two-layer URL validation, port allow-list, rate and concurrency limits |
| Audited website (untrusted content) | Redirects or DNS answers pointing at internal addresses; oversized or slow responses; malformed HTML/JSON-LD; text crafted to manipulate an AI model | Per-request and per-redirect revalidation, DNS filtering at connect time, size/time caps, tolerant parsers, no LLM in the core path |
| Browser viewing results | Script injection through crawled text or URLs | React escaping, http(s)-only links, strict CSP |
| Operator environment | Secrets leaking into child processes or logs | Minimal child environment, no secrets in logs or the database |

## Controls

### URL admission (API layer, `backend/brand_platform/urlsafety.py`)
- Only `http`/`https`; scheme-only strings such as `javascript:` are rejected. No embedded credentials. No whitespace,
  control characters or backslashes. Length ≤ 2048.
- Ports limited to `BRAND_PLATFORM_ALLOWED_PORTS` (default 80, 443).
- `localhost`, `*.localhost`, `*.local`, `*.internal`, `*.lan`, `*.home.arpa`, `*.onion`, cloud metadata hostnames and
  single-label hosts (which also covers decimal/hex IPv4 spellings) are refused.
- The hostname is resolved, and **every** answer must be globally routable (`is_global` and not private, loopback,
  link-local, multicast, reserved or unspecified). IPv4-mapped, 6to4 and NAT64 addresses are judged by the embedded IPv4
  address; Teredo is refused. A mixed public/private answer set is rejected as a rebinding pattern.
- Tests: `backend/tests/test_urlsafety.py` (50 cases, including a parity check against the engine's rule).

### Per-request enforcement (engine, all three skill scripts)
- Every fetch, every redirect hop and the final URL are revalidated (`_validate_public_http_url`).
- `_guarded_dns()` filters `getaddrinfo` answers at connect time, which narrows the DNS-rebinding window between
  validation and connection.
- Responses are read up to 2 MB; 10 s socket timeouts; at least 0.5 s between requests to a host, or longer if
  robots.txt declares a `Crawl-delay`.
- robots.txt is checked before every page fetch. **D13** (the trust stage ignored disallow rules) was fixed in session 1
  and is covered by `tests/test_engine_fixes.py::TestTrustRobotsGate` and the backend end-to-end test
  `test_robots_disallowed_site_is_partial_not_clean`, which asserts that only `/robots.txt` was requested.
- Headless rendering is **disabled** in the platform (`BRAND_AUDIT_DISABLE_RENDER=1`) because a browser's own network
  stack bypasses these checks.

### Process isolation and limits (`runner.py`)
- Each audit runs `run_audit.py` in its own process group with a **minimal environment**: only PATH, temp and locale
  variables, proxy and CA settings, and the engine switches. API keys and passwords in the server environment are not
  inherited (tested).
- Hard kill of the whole process tree at runtime limit + grace; cancellation kills the tree too (both tested).
- `BRAND_PLATFORM_MAX_CONCURRENT_JOBS` (default 2), queue cap (default 10), one active audit per host, and a creation
  rate limit per client address (default 12 per 10 minutes, in memory, single node).

### API and browser
- Consistent error envelope `{error: {code, message, request_id}}`. Internal exceptions return a generic 500 message;
  stack traces are not sent to clients.
- Request IDs: a client value is accepted only if it matches `^[A-Za-z0-9-]{8,64}$`; otherwise a new one is generated.
- Headers: `Content-Security-Policy` (`default-src 'self'`, no inline script **or** style; bars are drawn as SVG so
  `unsafe-inline` is not needed), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
  `/api/docs` (Swagger UI) is exempt from the CSP because it loads assets from a CDN.
- CORS allows only the configured dev origins and the methods GET and POST.
- The UI renders crawled text as text (React escaping, no `dangerouslySetInnerHTML`), and links only `http:`/`https:`
  URLs with `rel="noopener noreferrer nofollow"`.
- SQL uses bound parameters; column names in dynamic UPDATEs come from a fixed allow-list.

### Data handling
- Stored: audit metadata, the composed report (findings and evidence snippets), and prioritisation. Not stored: raw
  page HTML, sub-audit working files (each job's work directory is deleted), or request headers.
- Logs are structured JSON with request id, path, status and duration. No request bodies and no secrets are logged.

## Known gaps (not implemented)
- **No authentication or authorisation.** Anyone who can reach the API can start audits and read every stored audit.
  Deploy it only on localhost or behind an authenticating reverse proxy.
- The rate limiter is in memory and keyed on the client IP; it resets on restart and does not account for proxies.
- `_guarded_dns()` monkey-patches `socket.getaddrinfo` process-wide. That is safe only because each audit runs in its own process.
- robots.txt network/5xx failures fail open (D11).
- No automatic data-retention purge.
- Optional LLM remediation (planned, M3) will need its own prompt-injection controls. Crawled text must be passed as quoted
  data, with no tool access, strict output validation, and a deterministic fallback.
