"""Offline publication checks: invented records only; no live network requests."""

import copy
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_final as join
import build_viewer_data as export
import companies
import fetch_all
import fetch_jobs
import filter_jobs as scorer

ROOT = Path(__file__).resolve().parents[1]


def posting(title="Data Analyst", company="Example Museum", url="https://example.invalid/jobs/1", **fields):
    return dict(title=title, company=company, url=url, location="Example City",
                description="Analyze visitor trends. 3+ years of analysis experience.", **fields)


class CriteriaChecks(unittest.TestCase):
    def test_neutral_defaults_keep_unrelated_roles_and_work_modes(self):
        for title, location in [("Research Lead", "Example City"), ("Design Intern", "Remote"),
                                ("Operations Coordinator", "Another Country")]:
            result = scorer.score({"title": title, "location": location, "description": "No experience requirement stated."})
            self.assertTrue(result["passes_criteria"])
            self.assertEqual(result["score"], 0)
            self.assertEqual(result["signal_tags"], "")

    def test_custom_rules_explain_rejection_without_losing_record(self):
        rules = scorer.load_criteria()
        rules.update(title_include=["analyst"], location_exclude=["Example"], weighted_terms=[
            {"label": "data", "pattern": "data|analyze", "weight": 2}])
        result = scorer.score(posting(), rules)
        self.assertFalse(result["passes_criteria"])
        self.assertIn("location matched", result["criteria_reasons"])
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["signal_tags"], "data")

    def test_unknown_experience_requires_explicit_rejection(self):
        rules = scorer.load_criteria()
        self.assertTrue(scorer.score({"title": "Writer"}, rules)["passes_criteria"])
        rules["include_unknown_experience"] = False
        self.assertFalse(scorer.score({"title": "Writer"}, rules)["passes_criteria"])

    def test_experience_bound_and_source_excerpt(self):
        rules = scorer.load_criteria()
        rules["max_required_years"] = 2
        result = scorer.score(posting(), rules)
        self.assertEqual(result["yoe"], "3+")
        self.assertIn("3+ years", result["qualifying_quote"])
        self.assertFalse(result["passes_criteria"])

    def test_work_mode_only_filters_when_configured(self):
        rules = scorer.load_criteria()
        rules["work_modes"] = ["hybrid"]
        self.assertFalse(scorer.score({"title": "Analyst", "location": "Remote"}, rules)["passes_criteria"])
        self.assertTrue(scorer.score({"title": "Analyst", "location": "Hybrid, 3 days remote"}, rules)["passes_criteria"])

    def test_salary_needs_context_and_never_converts(self):
        self.assertIsNone(scorer.parse_comp("Operating budget: $100,000-$200,000"))
        self.assertEqual(scorer.parse_comp("Salary range $70K-$90K annually"), (70000, 90000))
        self.assertEqual(scorer.parse_comp("Base pay $25-$30 per hour"), (25, 30))

    def test_invalid_configuration_rejected(self):
        for supplied in [{"unknown": []}, {"max_required_years": -1}, {"title_include": ["["]},
                         {"weighted_terms": [{"label": "x", "pattern": "x", "weight": float("inf")}]},
                         {"work_modes": ["sometimes"]}, {"min_required_years": 3, "max_required_years": 2}]:
            with self.subTest(supplied=supplied), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "criteria.json"
                path.write_text(json.dumps(supplied), encoding="utf-8")
                with self.assertRaises((ValueError, __import__("re").error)):
                    scorer.load_criteria(path)


class JoinChecks(unittest.TestCase):
    def test_exact_url_takes_priority_over_title_candidate(self):
        intake = [posting()]
        same = posting(title="Updated Analyst Title")
        decoy = posting(url="https://example.invalid/jobs/2")
        result = join.join_records(intake, [decoy, same])
        matched = result[0]
        self.assertEqual(matched["match_confidence"], "same-url")
        self.assertEqual(matched["matched_title"], "Updated Analyst Title")
        self.assertEqual(matched["status"], "needs_review")
        self.assertEqual(len(result), 2)

    def test_company_title_is_candidate_not_verified(self):
        intake = [{"title": "Data Analyst", "company": "Example Museum", "url": ""}]
        result = join.join_records(intake, [posting()])
        self.assertEqual(result[0]["match_confidence"], "company-title-candidate")
        self.assertEqual(result[0]["status"], "needs_review")

    def test_ambiguous_requisitions_do_not_choose_description(self):
        intake = [{"title": "Data Analyst", "company": "Example Museum"}]
        result = join.join_records(intake, [posting(), posting(url="https://example.invalid/jobs/2")])
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["match_confidence"], "ambiguous-company-title")
        self.assertEqual(result[0]["description"], "")
        self.assertEqual(result[0]["candidate_count"], 2)

    def test_empty_observation_does_not_shadow_complete_description(self):
        complete = posting()
        empty = {**posting(), "description": ""}
        result = join.dedupe_postings([complete, empty])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["description"])

    def test_missing_urls_do_not_merge_separate_observations(self):
        records = [posting(url=""), {**posting(url=""), "description": "A different source observation"}]
        self.assertEqual(len(join.dedupe_postings(records)), 2)

    def test_fuzzy_candidate_is_labeled_and_target_only_cannot_be_reused(self):
        intake = [{"title": "Data Analyst", "company": "Example Museum"}]
        candidate = posting(title="Senior Data Analyst")
        self.assertEqual(join.join_records(intake, [candidate])[0]["match_confidence"], "fuzzy-title-candidate")
        candidate["exact_target_only"] = True
        self.assertEqual(join.join_records(intake, [candidate])[0]["match_confidence"], "unmatched")

    def test_missing_intake_rows_and_extra_employers_remain_visible(self):
        intake = [{"title": "Writer", "company": "Example Publisher"}]
        result = join.join_records(intake, [posting()])
        self.assertEqual([r["match_confidence"] for r in result], ["unmatched", "collected-only"])
        self.assertTrue(all(r["passes_criteria"] for r in result))

    def test_url_validation_rejects_credentials_and_nonweb_schemes(self):
        for url in ["file:///local/private", "javascript:alert(1)", "https://user:pass@example.invalid", "https://[broken"]:
            self.assertEqual(join.safe_url(url), "")
        self.assertEqual(join.safe_url("https://example.invalid/job"), "https://example.invalid/job")


class PipelineChecks(unittest.TestCase):
    def test_browser_export_flags_candidate_and_rejects_invalid_identity(self):
        record = export.import_record({**posting(), "match_confidence": "fuzzy-title-candidate", "status": "reviewed"}, 0)
        self.assertEqual(record["status"], "needs_review")
        self.assertIn("candidate description", record["open_questions"][0])
        self.assertEqual(record["source_url"], "https://example.invalid/jobs/1")
        with self.assertRaises(ValueError):
            export.import_record({"title": "", "company": "Example"}, 0)

    def test_public_fixture_end_to_end_without_changing_it(self):
        fixture = ROOT / "demo" / "data.json"
        original = fixture.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            combined = Path(temp) / "combined.csv"
            output = Path(temp) / "import.json"
            subprocess.run([sys.executable, str(ROOT / "build_final.py"), "--postings", str(fixture),
                            "--output", str(combined)], check=True, capture_output=True)
            count = export.build(combined, output)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(count, 16)
            self.assertTrue(all(r["status"] == "needs_review" for r in data["jobs"]))
            self.assertTrue(all(r["title"] and r["company"] for r in data["jobs"]))
            with combined.open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(all(r["score"] == "0" and r["passes_criteria"] == "True" for r in rows))
        self.assertEqual(fixture.read_bytes(), original)

    def test_empty_export_is_rejected_for_browser_compatibility(self):
        with tempfile.TemporaryDirectory() as temp:
            combined = Path(temp) / "empty.csv"
            combined.write_text("title,company\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                export.build(combined, Path(temp) / "import.json")

    def test_adapter_normalization_uses_mock_payload_only(self):
        payload = {"jobs": [{"title": "Archive Researcher", "location": {"name": "Example City"},
                              "absolute_url": "https://example.invalid/jobs/3",
                              "content": "&lt;p&gt;Read &amp; catalog records.&lt;/p&gt;"}]}
        result = fetch_jobs.normalize("greenhouse", "example-token", payload)
        self.assertEqual(result[0]["description"], "Read & catalog records.")
        self.assertEqual(result[0]["vertical"], "unknown")
        with patch.object(fetch_all, "list_simple", return_value=[{"title": "Archive Researcher", "desc": "Example"}]):
            _board, jobs = fetch_all.handle_board({"ats": "greenhouse", "handle": "example-token", "company": "Example"})
        self.assertEqual(len(jobs), 1)

    def test_collectors_require_explicit_inventory(self):
        for script in ("fetch_jobs.py", "fetch_all.py"):
            result = subprocess.run([sys.executable, str(ROOT / script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("required", result.stderr)
        self.assertEqual(companies.load_seeds(ROOT / "examples" / "seeds.example.json"), ([], {}))


if __name__ == "__main__":
    unittest.main()
