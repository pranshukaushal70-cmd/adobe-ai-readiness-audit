# Project Audit — Baseline of the Brand AI-Readiness Audit Package

Audit date: 2026-10-23. Auditor: Claude Code (AI assistant), working on behalf of the project owner.
Scope: every file in the original package (22 files). All behaviour claims below were checked
by reading the implementation and/or running it on this machine. Nothing here relies on README claims alone.

## 1. Environment

| Item | Observed |
|---|---|
| OS | Windows 10 Pro 10.0.19045 |
| Python | 3.12.3 (system install) |
| Node / npm | v24.21.0 / 11.19.0 |
| Version control | **None** — the directory is not a Git repository. No branch could be created; a byte-for-byte snapshot of the original 22 files was taken before any edit. |
| Installed relevant Python packages | `playwright 1.63.0` (with Chromium downloaded), `httpx 0.28.1`, `Jinja2 3.1.6`. No FastAPI, pytest, or PDF library. |
| Network | Outbound HTTPS to PyPI/npm works. |

## 2. What the original package is

A Python **Agent Skill Marketplace** (`marketplace.json` v1.4.0) with four skills:

| Skill | Script | Lines | Role |
|---|---|---|---|
| `audit-orchestrator` (entrypoint) | `scripts/run_audit.py`, `scripts/compose_report.py` | 171 + 766 | Runs the three sub-audits as subprocesses with per-stage (60 s) and whole-pipeline (240 s) timeouts, then composes one JSON report. |
| `crawl-render-audit` | `scripts/check_technical.py` | 1527 | robots.txt, sitemaps, bounded same-domain crawl (≤ `--max-pages`), JSON-LD, canonical, noindex, redirects, fact parity, image alt/canvas, viewport, optional Playwright render gap. |
| `freshness-corroboration` | `scripts/check_trust.py` | 1075 | Multi-signal freshness, E-E-A-T/contact signals, sameAs sanity, Wikipedia/Wikidata corroboration, entity-confidence score. |
| `engagement-audit` | `scripts/check_engagement.py` | 840 | H1, readability, CTA intent classification, navigation/dead-ends, answerability/quote-readiness, deep-link context, clutter. |

Core runtime is the Python standard library only. Playwright is optional. The CLI JSON output contract is
documented in `skills/audit-orchestrator/SKILL.md` and is produced by `compose_report.py`.

### Architecture as implemented

```
run_audit.py ──subprocess──▶ check_technical.py ──▶ technical.json ─┐
             ──subprocess──▶ check_trust.py --technical ──▶ trust.json ├─▶ compose_report.py ──▶ final report JSON
             ──subprocess──▶ check_engagement.py --technical ─▶ engagement.json ┘
```

The technical stage's `crawl_scope.crawled_urls` is used as the shared representative page set for the trust and
engagement stages (verified in `run_audit.py:102-116` and both scripts' `__main__` blocks).

## 3. Baseline test results (actually executed)

| Command | Result |
|---|---|
| `python tests/test_all_rubric_cases.py` | **Ran 43 tests, OK.** README claims 48; 5 tests in `TestPolishEnhancements` are defined *after* `unittest.main()` (line 591) and never run in script mode. They are collected by pytest. |
| `python tests/test_round3_polish.py` | **Ran 20, FAILED (errors=1)** on Windows: `test_no_fake_adobe_score_language` calls `read_text()` without `encoding=` → `UnicodeDecodeError` under the cp1252 locale. Passes with `PYTHONUTF8=1`. |
| `python verify_marketplace.py` | **exit 1** on Windows (same encoding error propagates). With `PYTHONUTF8=1`: **exit 0**, all stages PASS, ~61 s runtime. |
| `examples/run_live_smoke_tests.ps1` | **Cannot run**: assigns `$host`, a read-only PowerShell automatic variable (`Cannot overwrite variable Host because it is read-only or constant.` reproduced). |

Additional test-quality observations:
- `tests/test_round3_polish.py` lines 184-208: two functions (`test_composer_marks_missing_subaudit_as_partial`,
  `test_network_failure_is_unavailable_not_antibot`) are indented inside the `if __name__ == '__main__':` block, so
  they are never collected or executed by any runner. They also reference names that do not exist
  (`subprocess`, `patch` are not imported; `check_technical.audit_site` and `check_technical.fetch` do not exist).
- `test_required_report_fields_are_preserved` asserts on a dict literal it constructs itself (tautological).
- `test_total_findings_strictly_excludes_proactive` re-implements the counting logic instead of exercising the composer.

## 4. Defects found by inspection and confirmed at runtime

| # | Severity | Location | Defect | Evidence |
|---|---|---|---|---|
| D1 | High | `compose_report.py:709-714` | Readiness index subtracts penalties for **proactive** suggestions although the method text says they do not reduce it. | Verifier report: technical = 74.4; recomputed without the proactive item = 81.1. |
| D2 | High | `compose_report.py` trust/engagement parsers | `affected_pages` is always `[site_url]` for trust and engagement findings, ignoring the per-check `affected_pages` the multi-page sub-audits compute. Deep-link failures are attributed to the homepage. | Code reading; verifier report shows `https://localhost` (a URL rebuilt from `--site localhost`) rather than the audited page. |
| D3 | High | `check_trust.py:553-599`, `check_engagement.py:691-709` + composer | When page fetches fail, checks are `unavailable`; the composer only reacts to `warning`/`fail`, so a category where nothing could be fetched yields **no defects and a proactive "no defect detected" suggestion**. Multi-page trust output also drops the `execution.errors` list. | Code reading (`_trust_status_rank` ranks `unavailable` below `warning`; composer has no `unavailable` branch for these categories). |
| D4 | Medium | `compose_report.py:695` | `scope.sitemap_checked` is true whenever the technical JSON has a `sitemap` key, which is always — including when robots.txt aborted the crawl before sitemap discovery ran. There is also no field saying whether a sitemap was *found*. | Code reading; regression test `test_d4_sitemap_not_checked_when_robots_aborts_crawl`. |
| D5 | Medium | `check_technical.py:1289` | `js_ev.append(...)` is referenced before `js_ev` is defined (line 1304). With Playwright installed, one page render failure raises `NameError`, which is swallowed and aborts rendering for **all** pages. | Code reading. |
| D6 | High (server context) | `check_technical.py:1274-1302`, `check_engagement.py:773-785` | Playwright rendering bypasses the SSRF guard: the browser fetches sub-resources and follows redirects with its own network stack. Acceptable for a local CLI, unsafe in a multi-user server. | Code reading. |
| D7 | Medium | `_validate_public_http_url` / `_is_public_ip` (all three scripts) | Allows `100.64.0.0/10` (carrier-grade NAT, `is_private` is False) and 6to4 `2002::/16` addresses that embed private IPv4. | Probe script: `http://100.64.0.1/` and `http://[2002:7f00:1::]/` ALLOWED. |
| D8 | Low | `check_trust.py:511` | Sitemap fetch failures are logged as "Wikipedia/Wikidata corroboration failed", which is misleading in `execution.errors`. | Verifier report shows this error although corroboration used mock data. |
| D9 | Low | `check_technical.py:1101-1107` + composer | A robots.txt self-disallow is reported under the title "HTTP requests blocked by anti-bot measures". | Code reading. |
| D10 | Low | `_guarded_dns()` (all scripts) | Monkey-patches `socket.getaddrinfo` process-wide; not thread-safe. Safe in the current subprocess design; would be unsafe if the scripts were imported into a multi-threaded server. | Code reading. Drives the design decision to keep subprocess isolation. |
| D11 | Low | `check_trust.py:224-239`, `check_engagement.py:756-771` | robots.txt fetch failures (network, 5xx) fail **open** (allowed). RFC 9309 recommends treating 5xx as "disallow all". 404 → allow is correct. | Code reading. |

### Found later, during implementation (session 1)

| # | Severity | Location | Defect | Evidence |
|---|---|---|---|---|
| D12 | Medium | `check_trust.py` `analyze_trust_pages` | Wikipedia/Wikidata were queried for **every** representative page, not once for the primary page as documented — up to 12 external calls with 8 s timeouts. | Regression test counts `check_external_apis` calls (was 3 for 3 pages). |
| D13 | **Critical** | `check_trust.py` `analyze_trust_pages` and `__main__` | `robots_allows()` returns `(allowed, robots_url)`; callers tested `if not robots_allows(u)`, which is never true for a non-empty tuple. The trust stage therefore **fetched pages that robots.txt disallows**. The original test hid it by mocking the function as returning `True`. | Found by the backend end-to-end test: with `Disallow: /` the fixture server logged requests for `/` and `/sitemap.xml`. |

All of D1–D8, D12 and D13 are fixed with regression tests; see `docs/CHANGE_LOG.md`. D9, D10 and D11 are documented
but unchanged.

## 5. What works and is reusable

- Subprocess orchestration with hard stage/global timeouts and partial-execution marking (`run_audit.py`).
- SSRF defences that are better than a string check: scheme allow-list, credential rejection, DNS resolution
  with public-IP check, per-redirect revalidation, final-URL revalidation, and DNS filtering at connect time
  (closes most of the DNS-rebinding window). Gaps: D6, D7.
- Bounded crawling: 2 MB response cap, 10 s timeouts, ≤6 pages, ≥0.5 s per-host spacing plus robots
  `Crawl-delay`, robots.txt checked before every crawled sub-page.
- Rich, explainable evidence strings and `how_to_fix` per finding; severity + confidence per finding.
- 63 passing unit/regression tests (43 + 20) plus an offline end-to-end verifier.

## 6. Gaps relative to the final-year platform goal

| Needed | Present? |
|---|---|
| Web API, job runner, progress, cancellation | No |
| Persistence, history, run comparison | No |
| Prioritisation beyond severity sort | Severity-then-confidence sort of the top 5 only |
| PDF report | No |
| Web UI | No |
| Labelled evaluation dataset / metrics | No (unit fixtures only) |
| Optional LLM remediation | No |
| CI, lint, type checks | No |

## 7. Risks

- **Package-hygiene coupling**: `verify_marketplace.py` walks the whole directory and asserts there is no
  `__pycache__`/`.pyc` anywhere. A virtualenv or `node_modules` inside the root would make it fail (and its
  cleanup step would walk tens of thousands of files). Mitigation: exclude third-party environment
  directories from that walk (documented change).
- **50 MB ZIP limit** for the original submission: new platform code must not be shipped inside the
  Adobe ZIP by accident; `node_modules`, `.venv`, and databases must be excluded.
- **No Git**: changes are tracked in `docs/CHANGE_LOG.md` and the snapshot; the owner is advised to `git init`.
- **Live-site variability**: real audits depend on network, WAFs, and Wikipedia/Wikidata availability; results
  are not reproducible across time and must not be used as evaluation ground truth.
