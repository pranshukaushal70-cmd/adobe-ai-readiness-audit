# Change Log

The directory is not under Git, so every change is recorded here. A byte-for-byte snapshot of the 22 original files
was taken before any edit (session scratchpad `original_snapshot/`); initialising Git is recommended so future
changes are reviewable as diffs.

## Session 1 — 2026-10-23

### Changes to original files (targeted patches; CLI flags and JSON output contract preserved)

| File | Change | Reason (see `docs/PROJECT_AUDIT.md`) |
|---|---|---|
| `skills/audit-orchestrator/scripts/compose_report.py` | Proactive suggestions excluded from the readiness index. | D1 |
| same | Trust/engagement findings use the check's own `affected_pages` (fallback: site URL). | D2 |
| same | New `collect_unavailable()`: `execution.unavailable_categories`, `execution.unavailable_checks`, `execution.failed_pages`; no proactive "clean" suggestion for a category with no usable evidence; such a category marks the report partial. | D3 |
| same | `scope.sitemap_checked` uses the technical stage's new `sitemap.checked` flag (legacy JSON keeps old behaviour); new `scope.sitemap_found` and `scope.audited_urls`. | D4 |
| same | `scope.external_sources_checked` is 0 when corroboration did not run. | Offline mode |
| `skills/crawl-render-audit/scripts/check_technical.py` | `js_ev` defined before the render block; stray re-initialisation removed. | D5 |
| same | `BRAND_AUDIT_DISABLE_RENDER=1` skips Playwright with an explicit "disabled" note. | D6 |
| same | `_is_public_ip` uses `is_global` and checks IPv4-mapped / 6to4 / NAT64 embedded addresses; Teredo refused. Validator uses it. | D7 |
| same | `sitemap.checked` flag; `crawl_scope.failed_urls` list. | D3, D4 |
| `skills/freshness-corroboration/scripts/check_trust.py` | Same public-IP rule. | D7 |
| same | 4xx robots.txt treated as "no restrictions" without logging an error (RFC 9309); sitemap 404/410 not an error; sitemap failures labelled correctly. | D8 |
| same | Multi-page output carries `execution.errors`; fetch exceptions are recorded. | D3 |
| same | Pages after the primary page no longer re-query Wikipedia/Wikidata. | D12 |
| same | `BRAND_AUDIT_OFFLINE=1` skips corroboration and reports it **unavailable** (never a pass). | Reproducible tests/evaluation |
| same | **robots.txt gate fixed**: `robots_allows()` returns a tuple, which was tested for truthiness, so disallowed pages were fetched in both the multi-page and single-page paths. | D13 |
| `skills/engagement-audit/scripts/check_engagement.py` | Public-IP rule; 4xx robots.txt handling; render-disable switch. | D6, D7, D8 |
| `skills/audit-orchestrator/scripts/run_audit.py` | Optional `--progress-file` writes per-stage state atomically. Without the flag behaviour is unchanged. | Platform progress |
| `verify_marketplace.py` | Hygiene walk skips `.venv`, `node_modules`, `.git` and tool caches; also runs `tests/test_engine_fixes.py`. | Local environments are not part of the package |
| `tests/test_all_rubric_cases.py` | `if __name__ == "__main__": unittest.main()` moved to the end of the file so all 48 tests run (43 ran before). No assertion changed. | Audit §3 |
| `tests/test_round3_polish.py` | `read_text()` → `read_text(encoding="utf-8")` (5 calls) so the suite passes on Windows. | Audit §3 |
| same | The mock of `check_trust.robots_allows` returned `True`; the real function returns `(allowed, robots_url)`. Mock corrected to the real return type; assertions unchanged. The invalid mock is what hid D13. | D13 |
| `examples/run_live_smoke_tests.ps1` | `$host` (read-only automatic variable) renamed `$siteHost`. | Script could not run |

Not changed: `marketplace.json`, every `SKILL.md`, every reference guide, `RUBRIC_MAPPING.md`.
The two dead functions at the end of `tests/test_round3_polish.py` were left as they are; working equivalents are in
`tests/test_engine_fixes.py::TestPortedDeadTests`.

### New files
- `tests/test_engine_fixes.py` — 24 regression tests for D1–D8, D12, D13.
- `backend/` — FastAPI platform (`brand_platform/`), 84 pytest tests, pinned requirements.
- `frontend/` — React + TypeScript + Vite UI, 18 Vitest tests.
- `docs/PROJECT_AUDIT.md`, `docs/IMPLEMENTATION_ROADMAP.md`, `docs/API_REFERENCE.md`, `docs/SECURITY.md`, this file.
- `.gitignore`.

### Test results at the end of the session (all run on Windows 10, Python 3.12.3, Node 24.21.0)
| Suite | Result |
|---|---|
| `python tests/test_all_rubric_cases.py` | 48 passed |
| `python tests/test_round3_polish.py` | 20 passed |
| `python tests/test_engine_fixes.py` | 24 passed |
| `python verify_marketplace.py` | exit 0 (no `PYTHONUTF8` needed) |
| `backend: pytest` | 84 passed (includes real end-to-end audits of a local fixture site) |
| `backend: ruff check .` | clean |
| `frontend: npm test` / `npm run build` | 18 passed / build OK; `tsc --noEmit` clean |
| Browser walkthrough (Playwright, local fixture) | Submit → progress → results → finding detail → re-audit → compare → history → dashboard; 390 px viewport has no horizontal overflow; the only console error is the deliberate 422 for a private IP. |
