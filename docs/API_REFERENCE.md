# API Reference

Base path `/api`. JSON in and out. Interactive OpenAPI docs: `/api/docs`; schema: `/api/openapi.json`.
Timestamps are UTC ISO-8601 (`2026-10-23T10:25:11Z`). Every response carries `X-Request-ID`.

## Errors

```json
{ "error": { "code": "non_public_address", "message": "Hostname 'x' resolves to a non-public address (10.0.0.5).", "request_id": "…" } }
```

| HTTP | Codes |
|---|---|
| 404 | `audit_not_found`, `not_found` |
| 409 | `host_busy`, `not_cancellable`, `report_not_ready` |
| 422 | `validation_error` (with `details: [{field, message}]`), `invalid_url`, `unsupported_scheme`, `credentials_in_url`, `port_not_allowed`, `non_public_host`, `non_public_address`, `dns_resolution_failed`, `same_audit` |
| 429 | `rate_limited`, `queue_full` |
| 500 | `internal_error` |

## Endpoints

| Method & path | Purpose |
|---|---|
| `GET /health` | `{status, version, schema_version}` |
| `GET /config` | Public limits: `max_pages_cap`, `default_max_pages`, `allowed_ports`, `max_concurrent_jobs`, `max_queued_jobs`, `runtime_limit_seconds`, `rendering_enabled`, `priority_model`, `engine_version` |
| `POST /audits` | Body `{url, max_pages?}` (1–6). Returns **202** with an `Audit` in status `queued`. |
| `GET /audits` | Query `status`, `q` (URL/host substring), `host`, `limit` (≤100), `offset`. Returns `{items, total, limit, offset}`, newest first. |
| `GET /audits/{id}` | One `Audit`, including live `progress.stages` while it runs. |
| `POST /audits/{id}/cancel` | Cancels a queued or running audit (409 otherwise). |
| `GET /audits/{id}/findings` | Query `category`, `severity`, `q`, `include_proactive`. Returns findings ordered by priority rank; suggestions last. |
| `GET /audits/{id}/report` | `{audit, report}`, where `report` is the engine's composed JSON report (contract in `skills/audit-orchestrator/SKILL.md`, plus the additive `execution` and `scope` fields listed in `docs/CHANGE_LOG.md`). |
| `GET /audits/{id}/report.json` | Download: `{export_format: "brand-ai-readiness/1", audit, report, prioritised_findings}` |
| `GET /audits/{id}/report.pdf` | Download: a PDF report covering scope, methodology, summary, severity chart, ranked recommendations with factors, finding details, and limitations. |
| `GET /compare?base=&target=` | Run diff: `persistent`, `new`, `resolved`, `inconclusive`, `counts`, `readiness_delta`, `caveats`. |

### Audit statuses
`queued` → `running` → one of `completed`, `partial` (the report exists but `execution.partial` is true), `failed`
(no valid report), `timed_out` (hard kill), `cancelled`, `interrupted` (the server stopped mid-run).

### Finding
`{id, audit_id, finding_code, fingerprint, title, category, severity, confidence, proactive, affected_pages, evidence,
suggested_action{summary, priority, how_to_fix}, priority{model, score, rank, factors[{name, value, input, explanation}]} | null}`.
`priority` is null for proactive suggestions. `fingerprint` (`category:slugified-title`) identifies the rule across runs.

## Example

```bash
curl -s -X POST localhost:8000/api/audits -H 'Content-Type: application/json' -d '{"url":"example.com","max_pages":3}'
curl -s localhost:8000/api/audits/<id>
curl -s localhost:8000/api/audits/<id>/findings
curl -s -o report.pdf localhost:8000/api/audits/<id>/report.pdf
```
