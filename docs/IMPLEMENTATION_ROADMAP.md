# Implementation Roadmap — Brand AI-Readiness Intelligence Platform

Status legend: ✅ done and tested · 🟡 in progress / partial · ⬜ planned (not started).
This file is updated at the end of every work session. "Done" means implemented **and** covered by a passing test.

## Target architecture (chosen for simplicity, not for appearance)

```
 React + TypeScript + Vite SPA  ──HTTP/JSON──▶  FastAPI (Python 3.12)
        (frontend/)                                (backend/brand_platform/)
                                                    │  URL safety pre-check (DNS, public IPs, ports)
                                                    │  Bounded job runner (thread pool, N concurrent, queue cap)
                                                    │      └─ subprocess: skills/audit-orchestrator/scripts/run_audit.py
                                                    │             (unchanged CLI contract; process isolation)
                                                    │  Deterministic prioritisation (explainable factors)
                                                    │  SQLite (stdlib sqlite3, versioned migrations)
                                                    └─ JSON + PDF (reportlab) export
```

Decisions and why:
- **Subprocess, not import**: the engine monkey-patches `socket.getaddrinfo` process-wide (audit D10). Running it in a
  child process keeps that safe and gives real hard-kill cancellation and timeouts.
- **SQLite via stdlib `sqlite3`**: one file, no server, no ORM dependency. Schema is plain SQL with a
  `schema_migrations` table, so a PostgreSQL port is a mechanical translation if ever needed.
- **No Redis/Celery**: audits are ≤ 6 pages and ≤ 240 s; a bounded in-process thread pool with a queue cap is
  sufficient for a single-node demo. Jobs that were running when the server stopped are marked `interrupted` at startup.
- **Rendering disabled in server mode**: Playwright bypasses the SSRF guard (audit D6), so the API runs the engine
  with `BRAND_AUDIT_DISABLE_RENDER=1`. Rendering stays available to the CLI.

## Milestones

### M0 — Baseline & audit ✅
- Snapshot, test baseline, defect list → `docs/PROJECT_AUDIT.md`.

### M1 — Engine correctness fixes (targeted patches, each with a regression test) ✅
Acceptance: original suites pass (48 + 20 tests), verifier exits 0 on Windows **without** `PYTHONUTF8`, and new
regression tests in `tests/test_engine_fixes.py` pass.
- D1 proactive items excluded from the readiness index.
- D2 per-check `affected_pages` propagated for trust/engagement.
- D3 unavailable checks surfaced (`execution.unavailable_checks`) and no proactive "clean" suggestion for a category
  whose checks were all unavailable; multi-page trust keeps `execution.errors`.
- D4 `sitemap_checked` reflects whether a sitemap was found.
- D5 `js_ev` NameError.
- D6 `BRAND_AUDIT_DISABLE_RENDER` switch.
- D7 public-IP rule uses `is_global` plus 6to4/Teredo/NAT64 embedded-address checks.
- D8 error label. Test-runner placement and encoding fixes. Smoke-script `$host` fix.
- D12 duplicate external queries; D13 trust stage ignored robots.txt disallow (found by the M2 end-to-end test).

### M2 — Vertical slice: submit → audit → persist → view → export ✅ (session 1)
Acceptance criteria:
1. `POST /api/audits` rejects unsafe URLs (scheme, credentials, private/reserved IPs, non-standard ports) with a
   structured 422 error; accepts public URLs and returns a job id.
2. The job runs the real engine in a subprocess, records stage progress, enforces a hard timeout, supports cancel.
3. Results (metadata, findings, evidence, prioritisation, report version) persist in SQLite and survive restart.
4. `GET /api/audits/{id}/report.json` and `/report.pdf` export the stored report.
5. History list, filtering, and run-to-run comparison (`resolved / new / persistent / inconclusive`).
6. The React UI performs the flow end-to-end against the real API; no hard-coded results.
7. Backend pytest suite + frontend unit tests pass; original regression suites still pass.

### M3 — Explainable intelligence & optional AI ⬜
- Optional LLM provider abstraction (env-configured, off by default) for remediation *explanations* only; strict
  input limits, timeouts, output schema validation, deterministic fallback text, page text passed as quoted untrusted
  data, never tools. Stored separately from rule outputs and labelled as generated.
- Unit tests with a fake provider for timeout, malformed output, and injection-laden page text.

### M4 — Research evaluation framework ⬜
- Versioned labelled fixture set (`evaluation/fixtures/v1/`): positive, negative, edge, malformed, adversarial
  HTML per detector; labelling guide with uncertainty notes.
- Offline harness serving fixtures locally; per-detector precision/recall/F1/FPR with denominators and class balance;
  runtime distribution; ablations (e.g. multi-signal freshness vs copyright-only; formatting-aware vs naive fact parity).
- Tables/charts generated only from harness output files.

### M5 — Hardening, CI, docs 🟡 (`SECURITY.md`, `API_REFERENCE.md`, `CHANGE_LOG.md` written; rest planned)
- GitHub Actions (or equivalent) running engine tests, backend pytest, frontend lint/type-check/tests, ruff.
- Remaining docs: `SYSTEM_ARCHITECTURE.md`, `API_REFERENCE.md`, `SECURITY.md`, `TESTING_AND_EVALUATION.md`,
  `LIMITATIONS.md`, `FINAL_YEAR_REPORT_OUTLINE.md`, `VIVA_PREPARATION.md`.
- Clean-install test from the documented steps; low-cost deployment notes (single VM / container, no paid services).

## Next session (recommended order)
1. M5 basics: CI workflow (engine suites, verifier, backend pytest + ruff, frontend typecheck + tests + build).
2. M4 evaluation harness: labelled fixture set v1 and metrics per detector, with results generated from harness output only.
3. M3 optional LLM remediation explanations behind a provider interface (off by default).
4. Remaining docs: SYSTEM_ARCHITECTURE, TESTING_AND_EVALUATION, LIMITATIONS, FINAL_YEAR_REPORT_OUTLINE, VIVA_PREPARATION.

## Known limitations carried forward
- Live audits are not reproducible over time (sites change; Wikipedia/Wikidata availability varies).
- The readiness index is an internal heuristic, not a validated measure and not an Adobe score.
- Single-node job runner: no horizontal scaling; in-flight jobs do not survive a restart (they are marked interrupted).
- D11 (robots.txt fail-open on network/5xx) is documented, not yet changed, because it alters crawl behaviour.
