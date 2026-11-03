import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, type Audit, type Finding } from "./api";
import { FindingsExplorer, filterFindings } from "./components/FindingsExplorer";
import { ProgressStepper } from "./components/ProgressStepper";
import { formatDuration, safeHref } from "./lib/format";
import { precheckAuditUrl } from "./lib/url";
import { latestPerHost } from "./pages/Dashboard";

const finding = (over: Partial<Finding>): Finding => ({
  id: 1, audit_id: "a", finding_code: "F-001", fingerprint: "technical:x", title: "Missing viewport", category: "technical",
  severity: "medium", confidence: 0.95, proactive: false, affected_pages: ["https://e.example/pricing"], evidence: "No viewport on 1 page.",
  suggested_action: { summary: "Add viewport", how_to_fix: "<meta name=viewport>" },
  priority: { model: "priority-v1", score: 38, rank: 1, factors: [{ name: "severity", value: 0.4, input: "medium", explanation: "x" }] },
  ...over,
});

describe("precheckAuditUrl", () => {
  it.each([
    ["example.com", "https://example.com/"],
    ["http://example.com/a#frag", "http://example.com/a"],
  ])("accepts %s", (input, out) => expect(precheckAuditUrl(input)).toEqual({ ok: true, url: out }));
  it.each(["", "ftp://x.com", "javascript:alert(1)", "http://user:pw@x.com", "http://localhost", "intranet", "a b.com"])(
    "rejects %s", (input) => expect(precheckAuditUrl(input).ok).toBe(false));
});

describe("formatting", () => {
  it("formats durations", () => {
    expect(formatDuration("2026-10-23T10:00:00Z", "2026-10-23T10:01:05Z")).toBe("1m 05s");
    expect(formatDuration(null, null)).toBe("—");
  });
  it("only links http(s)", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("https://e.example/")).toBe("https://e.example/");
  });
});

describe("filterFindings", () => {
  const items = [finding({ id: 1 }), finding({ id: 2, category: "trust", severity: "high", title: "Fact contradiction" }),
    finding({ id: 3, proactive: true, priority: null, title: "Add anchors" })];
  it("filters by category, severity, search, and suggestions", () => {
    const base = { query: "", category: "" as const, severity: "" as const, showProactive: true };
    expect(filterFindings(items, base)).toHaveLength(3);
    expect(filterFindings(items, { ...base, category: "trust" }).map((f) => f.id)).toEqual([2]);
    expect(filterFindings(items, { ...base, severity: "medium" }).map((f) => f.id)).toEqual([1]);
    expect(filterFindings(items, { ...base, showProactive: false })).toHaveLength(2);
    expect(filterFindings(items, { ...base, query: "pricing" })).toHaveLength(3);
    expect(filterFindings(items, { ...base, query: "contradiction" }).map((f) => f.id)).toEqual([2]);
  });
});

describe("FindingsExplorer", () => {
  it("expands a finding to show evidence, fix, and the score breakdown", async () => {
    render(<FindingsExplorer findings={[finding({}), finding({ id: 2, title: "Other", severity: "high" })]} />);
    const button = screen.getByRole("button", { name: /Missing viewport/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("No viewport on 1 page.")).toBeInTheDocument();
    expect(screen.getByText(/Why it ranks #1/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Severity"), "high");
    expect(screen.queryByRole("button", { name: /Missing viewport/ })).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 2")).toBeInTheDocument();
  });
});

describe("ProgressStepper", () => {
  it("shows each stage's state", () => {
    render(<ProgressStepper stages={{ technical: "completed", trust: "running", engagement: "pending", compose: "pending" }} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    expect(within(items[0]!).getByText(/Done/)).toBeInTheDocument();
    expect(items[1]).toHaveAttribute("data-state", "running");
    expect(screen.getByText("1 of 4 stages complete.")).toBeInTheDocument();
  });
});

describe("latestPerHost", () => {
  const a = (id: string, host: string, created: string, status: Audit["status"], score: number): Audit => ({
    id, url: `https://${host}/`, host, status, max_pages: 4, created_at: created, started_at: null, finished_at: null, progress: {},
    error: null, readiness_score: score, readiness_band: null, total_findings: 0, critical_count: 0, high_count: 0, medium_count: 0,
    proactive_count: 0, pages_checked: 1, partial: false, engine_version: null, report_version: status === "failed" ? null : 1,
  });
  it("keeps only the newest run with a report for each host", () => {
    const out = latestPerHost([a("1", "x.com", "2026-01-01", "completed", 50), a("2", "x.com", "2026-02-01", "partial", 70),
      a("3", "x.com", "2026-03-01", "failed", 0), a("4", "y.com", "2026-01-05", "completed", 40)]);
    expect(out.map((o) => o.id)).toEqual(["4", "2"]);
  });
});

describe("api client", () => {
  afterEach(() => vi.restoreAllMocks());
  it("turns the error envelope into an ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      error: { code: "non_public_address", message: "Blocked", request_id: "req-123456" } }), { status: 422 }));
    const err = await api.createAudit("http://10.0.0.1", 2).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 422, code: "non_public_address", message: "Blocked", requestId: "req-123456" });
  });
  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.config()).rejects.toMatchObject({ code: "network_error" });
  });
});

it("renders inside a router without crashing", () => {
  render(<MemoryRouter><ProgressStepper /></MemoryRouter>);
  expect(screen.getAllByText(/Waiting/)).toHaveLength(4);
});
