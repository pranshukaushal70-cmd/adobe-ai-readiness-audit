#!/usr/bin/env python3
"""Regression tests for the engine defects recorded in docs/PROJECT_AUDIT.md (D1-D8).

Each test names the defect it guards. They use offline fixtures and mocks only, so they
are deterministic and do not touch the network.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
for p in [
    ROOT / "skills" / "crawl-render-audit" / "scripts",
    ROOT / "skills" / "engagement-audit" / "scripts",
    ROOT / "skills" / "freshness-corroboration" / "scripts",
    ROOT / "skills" / "audit-orchestrator" / "scripts",
]:
    sys.path.insert(0, str(p))

import check_engagement
import check_technical
import check_trust
import compose_report

COMPOSER = ROOT / "skills" / "audit-orchestrator" / "scripts" / "compose_report.py"


def compose(tech=None, trust=None, engagement=None, site="https://example.com"):
    """Run the real composer CLI on in-memory sub-audit dicts and return the report."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cmd = [sys.executable, str(COMPOSER), "--site", site, "--output", str(d / "out.json")]
        for name, data in (("technical", tech), ("trust", trust), ("engagement", engagement)):
            if data is not None:
                (d / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
                cmd += [f"--{name}", str(d / f"{name}.json")]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return json.loads((d / "out.json").read_text(encoding="utf-8"))


CLEAN_TECH = {"robots_txt": {"status": "found", "sitemaps": ["https://example.com/sitemap.xml"]},
              "crawler_block": {"status": "pass", "evidence": "ok"},
              "viewport_check": {"status": "pass", "evidence": "ok"},
              "structured_data": {"status": "pass", "evidence": "ok"},
              "crawl_scope": {"pages_successfully_crawled": 2}}
CLEAN_TRUST = {"copyright": {"status": "pass", "evidence": "ok"},
               "multi_signal_freshness": {"status": "pass", "evidence": "ok"},
               "eeat_check": {"status": "pass", "evidence": "ok"}}
CLEAN_ENG = {"h1_audit": {"status": "pass", "evidence": "ok"},
             "readability": {"status": "pass", "evidence": "ok"},
             "navigation_cta": {"status": "pass", "evidence": "ok"}}
UNAVAILABLE = {"status": "unavailable", "evidence": "Page fetch failed."}


class TestReadinessIndex(unittest.TestCase):
    def test_d1_proactive_suggestions_do_not_reduce_readiness(self):
        """D1: a report containing only proactive suggestions scores 100 in every dimension."""
        report = compose(CLEAN_TECH, CLEAN_TRUST, CLEAN_ENG)
        self.assertEqual(report["summary"]["total_findings"], 0)
        self.assertEqual(report["summary"]["proactive_suggestions_count"], 3)
        self.assertEqual(report["readiness"]["dimensions"], {"technical": 100.0, "trust": 100.0, "engagement": 100.0})
        self.assertEqual(report["readiness"]["score"], 100.0)

    def test_d1_defects_still_reduce_readiness(self):
        tech = dict(CLEAN_TECH, viewport_check={"status": "warning", "evidence": "no viewport", "confidence": 1.0})
        report = compose(tech, CLEAN_TRUST, CLEAN_ENG)
        self.assertEqual(report["readiness"]["dimensions"]["technical"], 93.0)


class TestAffectedPages(unittest.TestCase):
    def test_d2_engagement_findings_keep_page_level_affected_urls(self):
        eng = dict(CLEAN_ENG, readability={"status": "warning", "evidence": "wall of text",
                                           "affected_pages": ["https://example.com/article"]})
        report = compose(CLEAN_TECH, CLEAN_TRUST, eng)
        f = next(x for x in report["findings"] if x["title"].startswith("Poor text readability"))
        self.assertEqual(f["affected_pages"], ["https://example.com/article"])

    def test_d2_trust_findings_keep_page_level_affected_urls(self):
        trust = dict(CLEAN_TRUST, eeat_check={"status": "warning", "evidence": "no author",
                                              "affected_pages": ["https://example.com/blog/post"]})
        report = compose(CLEAN_TECH, trust, CLEAN_ENG)
        f = next(x for x in report["findings"] if "E-E-A-T" in x["title"])
        self.assertEqual(f["affected_pages"], ["https://example.com/blog/post"])

    def test_d2_falls_back_to_site_url_when_no_pages_reported(self):
        eng = dict(CLEAN_ENG, h1_audit={"status": "fail", "severity": "high", "evidence": "no h1"})
        report = compose(CLEAN_TECH, CLEAN_TRUST, eng)
        f = next(x for x in report["findings"] if "H1" in x["title"])
        self.assertEqual(f["affected_pages"], ["https://example.com"])


class TestUnavailableChecks(unittest.TestCase):
    def test_d3_unfetchable_engagement_is_not_reported_clean(self):
        eng = {k: dict(UNAVAILABLE) for k in ("h1_audit", "readability", "navigation_cta", "answerability",
                                              "deep_link_context", "clutter")}
        report = compose(CLEAN_TECH, CLEAN_TRUST, eng)
        self.assertTrue(report["execution"]["partial"])
        self.assertIn("engagement", report["execution"]["unavailable_categories"])
        self.assertFalse(any(f["category"] == "engagement" and f.get("proactive") for f in report["findings"]))
        self.assertTrue(any(c["category"] == "engagement" and c["check"] == "h1_audit"
                            for c in report["execution"]["unavailable_checks"]))

    def test_d3_unfetchable_trust_is_not_reported_clean(self):
        trust = {"copyright": dict(UNAVAILABLE), "multi_signal_freshness": dict(UNAVAILABLE),
                 "eeat_check": dict(UNAVAILABLE)}
        report = compose(CLEAN_TECH, trust, CLEAN_ENG)
        self.assertIn("trust", report["execution"]["unavailable_categories"])
        self.assertFalse(any(f["category"] == "trust" and f.get("proactive") for f in report["findings"]))

    def test_d3_network_failure_is_not_reported_clean_technical(self):
        tech = {"robots_txt": {"status": "not_found"},
                "crawler_block": {"status": "unavailable", "evidence": "no response"},
                "structured_data": dict(UNAVAILABLE), "viewport_check": dict(UNAVAILABLE),
                "faq_schema_check": dict(UNAVAILABLE), "locked_content": dict(UNAVAILABLE)}
        report = compose(tech, CLEAN_TRUST, CLEAN_ENG)
        self.assertIn("technical", report["execution"]["unavailable_categories"])
        self.assertFalse(any(f["category"] == "technical" and f.get("proactive") for f in report["findings"]))

    def test_d3_single_unavailable_check_does_not_mark_partial(self):
        """Render being unavailable is listed but does not make the whole report partial."""
        tech = dict(CLEAN_TECH, js_render_gap={"status": "unavailable", "evidence": "no browser"})
        report = compose(tech, CLEAN_TRUST, CLEAN_ENG)
        self.assertFalse(report["execution"]["partial"])
        self.assertEqual(report["execution"]["unavailable_categories"], [])
        self.assertTrue(any(c["check"] == "js_render_gap" for c in report["execution"]["unavailable_checks"]))

    def test_d3_failed_pages_are_listed(self):
        eng = dict(CLEAN_ENG, page_reports=[{"url": "https://example.com/", "status": "pass"},
                                            {"url": "https://example.com/broken", "status": "unavailable"}])
        tech = dict(CLEAN_TECH, crawl_scope={"pages_successfully_crawled": 1, "pages_failed": 1,
                                             "failed_urls": ["https://example.com/gone"]})
        report = compose(tech, CLEAN_TRUST, eng)
        self.assertIn("https://example.com/broken", report["execution"]["failed_pages"])
        self.assertIn("https://example.com/gone", report["execution"]["failed_pages"])

    def test_d3_multi_page_trust_keeps_execution_errors(self):
        def failing_fetch(url):
            msg = check_trust._record_execution_error(f"Page fetch blocked/failed for {url}", OSError("boom"))
            return f"Error: {msg}", None
        with patch.object(check_trust, "fetch_page_with_headers", side_effect=failing_fetch), \
                patch.object(check_trust, "robots_allows", return_value=(True, "")):
            out = check_trust.analyze_trust_pages(["https://example.com/", "https://example.com/a"],
                                                  current_year=2026, primary_external=lambda _b: [])
        self.assertTrue(out["execution"]["partial"])
        self.assertEqual(len(out["execution"]["errors"]), 2)


class TestScopeMetadata(unittest.TestCase):
    def _robots_disallow_fetch(self, url, **kwargs):
        if url.endswith("/robots.txt"):
            return 200, "User-agent: *\nDisallow: /\n", {}
        raise AssertionError(f"Fetched {url} although robots.txt disallows it")

    def test_d4_sitemap_not_checked_when_robots_aborts_crawl(self):
        tech = check_technical.analyze_technical("https://example.com/", fetch_fn=self._robots_disallow_fetch)
        self.assertFalse(tech["sitemap"]["checked"])
        report = compose(tech, CLEAN_TRUST, CLEAN_ENG)
        self.assertFalse(report["scope"]["sitemap_checked"])
        self.assertFalse(report["scope"]["sitemap_found"])

    def test_d4_legacy_technical_json_keeps_old_behaviour(self):
        report = compose(CLEAN_TECH, CLEAN_TRUST, CLEAN_ENG)
        self.assertTrue(report["scope"]["sitemap_checked"])


def _fake_site_fetch(url, **kwargs):
    if url.endswith("/robots.txt"):
        return 404, "", {}
    if url.rstrip("/") in ("https://example.com", "https://example.com/about"):
        html = ("<html><head><title>Example Co</title><meta name='viewport' content='width=device-width'></head>"
                "<body><h1>Example Co builds tools</h1><a href='/about'>About us</a></body></html>")
        return 200, html, {"_final_url": url, "_redirect_chain": []}
    return 404, "", {}


class TestRendering(unittest.TestCase):
    def _install_fake_playwright(self, goto_side_effect):
        fake = MagicMock()
        page = fake.sync_playwright.return_value.__enter__.return_value.chromium.launch.return_value \
            .new_context.return_value.new_page.return_value
        page.goto.side_effect = goto_side_effect
        sys.modules["playwright"] = fake
        sys.modules["playwright.sync_api"] = fake
        return fake

    def tearDown(self):
        sys.modules.pop("playwright", None)
        sys.modules.pop("playwright.sync_api", None)
        os.environ.pop("BRAND_AUDIT_DISABLE_RENDER", None)

    def test_d5_one_render_failure_does_not_abort_rendering(self):
        os.environ.pop("BRAND_AUDIT_DISABLE_RENDER", None)
        self._install_fake_playwright(RuntimeError("navigation boom"))
        tech = check_technical.analyze_technical("https://example.com/", max_crawl_pages=2, fetch_fn=_fake_site_fetch)
        ev = tech["js_render_gap"]["evidence"]
        self.assertIn("Render failed for https://example.com/", ev)
        self.assertNotIn("js_ev", ev)

    def test_d6_render_can_be_disabled_by_environment(self):
        os.environ["BRAND_AUDIT_DISABLE_RENDER"] = "1"
        fake = self._install_fake_playwright(None)
        tech = check_technical.analyze_technical("https://example.com/", max_crawl_pages=2, fetch_fn=_fake_site_fetch)
        self.assertEqual(tech["js_render_gap"]["status"], "unavailable")
        self.assertIn("disabled", tech["js_render_gap"]["evidence"].lower())
        fake.sync_playwright.assert_not_called()
        _, _, err = check_engagement.render_engagement_metrics("https://example.com/")
        self.assertIn("disabled", err.lower())


class TestPublicAddressRule(unittest.TestCase):
    BLOCKED = ["http://100.64.0.1/", "http://[2002:7f00:1::]/", "http://[2002:a00:1::]/",
               "http://[2001:0:4136:e378:8000:63bf:3fff:fdd2]/", "http://[64:ff9b::a00:1]/",
               "http://127.0.0.1/", "http://169.254.169.254/", "http://[::ffff:10.0.0.1]/",
               "http://192.168.1.1:8080/", "http://[fe80::1]/", "http://240.0.0.1/"]
    ALLOWED = ["http://8.8.8.8/", "http://[2606:4700:4700::1111]/", "http://[64:ff9b::808:808]/"]

    def test_d7_validators_block_non_public_addresses_in_every_skill(self):
        os.environ.pop("BRAND_AUDIT_LOCAL_FIXTURE", None)
        for module in (check_technical, check_trust, check_engagement):
            for url in self.BLOCKED:
                with self.subTest(module=module.__name__, url=url):
                    with self.assertRaises(ValueError):
                        module._validate_public_http_url(url)
            for url in self.ALLOWED:
                with self.subTest(module=module.__name__, url=url):
                    self.assertTrue(module._validate_public_http_url(url))


def _http_error(code):
    return urllib.error.HTTPError("https://example.com/x", code, "err", {}, None)


class TestErrorLabelling(unittest.TestCase):
    def setUp(self):
        check_trust.EXECUTION_ERRORS.clear()
        check_engagement.EXECUTION_ERRORS.clear()

    def test_d8_missing_sitemap_is_not_an_execution_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            self.assertIsNone(check_trust.fetch_sitemap_lastmod("https://example.com"))
        self.assertEqual(check_trust.EXECUTION_ERRORS, [])

    def test_d8_sitemap_failure_is_not_labelled_as_corroboration(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(500)):
            check_trust.fetch_sitemap_lastmod("https://example.com")
        self.assertTrue(check_trust.EXECUTION_ERRORS)
        self.assertNotIn("Wikipedia", check_trust.EXECUTION_ERRORS[0])
        self.assertIn("sitemap", check_trust.EXECUTION_ERRORS[0].lower())

    def test_missing_robots_txt_is_allowed_without_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            allowed, _ = check_trust.robots_allows("https://example.com/")
            self.assertTrue(allowed)
            self.assertTrue(check_engagement.robots_allows("https://example.com/"))
        self.assertEqual(check_trust.EXECUTION_ERRORS, [])
        self.assertEqual(check_engagement.EXECUTION_ERRORS, [])


class TestExternalCorroboration(unittest.TestCase):
    PAGES = {u: f"<html><head><title>Acme</title></head><body><p>Page {i}</p><a href='/contact'>Contact</a></body></html>"
             for i, u in enumerate(["https://acme.example/", "https://acme.example/a", "https://acme.example/b"])}

    def tearDown(self):
        os.environ.pop("BRAND_AUDIT_OFFLINE", None)

    def test_d12_external_apis_are_queried_once_for_multi_page_trust(self):
        with patch.object(check_trust, "fetch_page_with_headers", side_effect=lambda u: (self.PAGES[u], None)), \
                patch.object(check_trust, "robots_allows", return_value=(True, "")), \
                patch.object(check_trust, "fetch_sitemap_lastmod", return_value=None), \
                patch.object(check_trust, "check_external_apis", return_value=[]) as external:
            out = check_trust.analyze_trust_pages(list(self.PAGES), current_year=2026)
        self.assertEqual(out["pages_checked"], 3)
        self.assertEqual(external.call_count, 1)

    def test_offline_mode_marks_corroboration_unavailable_not_pass(self):
        os.environ["BRAND_AUDIT_OFFLINE"] = "1"
        with patch.object(check_trust, "fetch_sitemap_lastmod", return_value=None), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network used in offline mode")):
            r = check_trust.analyze_trust(self.PAGES["https://acme.example/"], "https://acme.example/", current_year=2026)
        self.assertEqual(r["corroboration_check"]["status"], "unavailable")
        self.assertIn("offline", r["corroboration_check"]["evidence"].lower())
        report = compose(CLEAN_TECH, r, CLEAN_ENG)
        self.assertEqual(report["scope"]["external_sources_checked"], 0)
        self.assertTrue(any(c["check"] == "corroboration_check" for c in report["execution"]["unavailable_checks"]))


class TestTrustRobotsGate(unittest.TestCase):
    def test_d13_multi_page_trust_respects_robots_disallow(self):
        """robots_allows returns a (allowed, url) tuple; a truthiness check let every page through."""
        with patch.object(check_trust, "robots_allows", return_value=(False, "https://example.com/robots.txt")), \
                patch.object(check_trust, "fetch_page_with_headers",
                             side_effect=AssertionError("fetched a robots-disallowed page")) as fetch:
            out = check_trust.analyze_trust_pages(["https://example.com/", "https://example.com/a"], current_year=2026)
        fetch.assert_not_called()
        self.assertTrue(all(r["status"] == "unavailable" for r in out["page_reports"]))
        self.assertIn("robots.txt", out["page_reports"][0]["multi_signal_freshness"]["evidence"])


class TestPortedDeadTests(unittest.TestCase):
    """Working versions of the two functions in test_round3_polish.py that were never collected."""

    def test_composer_marks_missing_subaudit_as_partial(self):
        with tempfile.TemporaryDirectory() as td:
            tech = Path(td) / "technical.json"
            tech.write_text(json.dumps({"robots_txt": {}, "crawl_scope": {"pages_successfully_crawled": 1},
                                        "js_render_gap": {"status": "unavailable"}}), encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPOSER), "--site", "https://example.com",
                                     "--technical", str(tech), "--trust", str(Path(td) / "missing-trust.json"),
                                     "--output", str(Path(td) / "report.json")], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            report = json.loads((Path(td) / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["execution"]["partial"])
            self.assertIn("trust", report["execution"]["missing_categories"])
            self.assertFalse(any(f.get("category") == "trust" and f.get("proactive") for f in report["findings"]))

    def test_network_failure_is_unavailable_not_antibot(self):
        def no_response(url, **kwargs):
            return 0, "temporary dns failure", {"_error": "Temporary failure in name resolution"}
        result = check_technical.analyze_technical("https://example.com", fetch_fn=no_response)
        self.assertEqual(result["crawler_block"]["status"], "unavailable")
        self.assertNotIn("anti-bot", result["crawler_block"]["evidence"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
