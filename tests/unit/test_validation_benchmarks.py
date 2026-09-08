"""AEGIS-Marine: Unit Test Suite for Automated Benchmark Validation Suite (TASK-053).

Tests:
1. Spatial polygon metric calculators (IoU, F1 score, False Discovery Rate).
2. Liu-Weisberg Lagrangian trajectory skill score and separation error.
3. Tier 1 SAR DeepLabv3+ segmentation benchmark execution and PRD Section 14 targets.
4. Tier 2 & Tier 3 Hydrodynamic drift and backtracking across >= 3 historical incidents.
5. Tier 4 AIS Correlation and Multi-Criteria attribution scoring across investigation cases.
6. CLI execution with flag arguments, threshold gates, and structured JSON export.
7. Constitutional Rule 6 terminology compliance across all benchmark outputs and reports.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import shapely.geometry
from scripts.lint_banned_terms import check_content
from scripts.run_validation_benchmarks import (
    BenchmarkMetricResult,
    SuiteSummary,
    compute_liu_weisberg_skill,
    compute_polygon_metrics,
    execute_benchmarks,
    export_json_report,
    main as run_benchmarks_main,
    run_tier1_benchmarks,
    run_tier3_benchmarks,
    run_tier4_benchmarks,
)


class TestValidationBenchmarksSuite(unittest.TestCase):
    """Test suite verifying the accuracy and robustness of the benchmark validation tool."""

    def test_compute_polygon_metrics_exact_cases(self) -> None:
        """Verifies polygon metric formulas on known synthetic geometric configurations."""
        # 1. Identical squares (10x10): Area = 100
        p1 = shapely.geometry.box(0, 0, 10, 10)
        p2 = shapely.geometry.box(0, 0, 10, 10)
        iou, f1, fdr, precision, recall = compute_polygon_metrics(p1, p2)
        self.assertAlmostEqual(iou, 1.0, places=4)
        self.assertAlmostEqual(f1, 1.0, places=4)
        self.assertAlmostEqual(fdr, 0.0, places=4)
        self.assertAlmostEqual(precision, 1.0, places=4)
        self.assertAlmostEqual(recall, 1.0, places=4)

        # 2. 50% horizontal overlap: P1=[0, 10], P2=[5, 15]
        # Inter = 50, Pred = 100, GT = 100, Union = 150
        # IoU = 50/150 = 0.3333, F1 = 100/200 = 0.50, FDR = (100 - 50)/100 = 0.50
        p_pred = shapely.geometry.box(0, 0, 10, 10)
        p_gt = shapely.geometry.box(5, 0, 15, 10)
        iou_half, f1_half, fdr_half, prec_half, rec_half = compute_polygon_metrics(p_pred, p_gt)
        self.assertAlmostEqual(iou_half, 1.0 / 3.0, places=4)
        self.assertAlmostEqual(f1_half, 0.50, places=4)
        self.assertAlmostEqual(fdr_half, 0.50, places=4)
        self.assertAlmostEqual(prec_half, 0.50, places=4)
        self.assertAlmostEqual(rec_half, 0.50, places=4)

        # 3. Disjoint polygons
        p_disjoint = shapely.geometry.box(20, 20, 30, 30)
        iou_d, f1_d, fdr_d, _, _ = compute_polygon_metrics(p_pred, p_disjoint)
        self.assertEqual(iou_d, 0.0)
        self.assertEqual(f1_d, 0.0)
        self.assertEqual(fdr_d, 1.0)

    def test_compute_liu_weisberg_skill_score_cases(self) -> None:
        """Verifies Lagrangian trajectory skill score on modeled vs observed trajectories."""
        # 1. Identical trajectories -> Skill score = 1.0, Separation = 0.0
        traj = [(72.0, 18.0), (72.1, 18.1), (72.2, 18.2), (72.3, 18.3)]
        ss_perf, s_perf = compute_liu_weisberg_skill(traj, traj)
        self.assertEqual(ss_perf, 1.0)
        self.assertEqual(s_perf, 0.0)

        # 2. Minimal separation divergence (< 0.10)
        modeled = [(72.002, 18.001), (72.103, 18.102), (72.204, 18.203), (72.3, 18.3)]
        ss_close, s_close = compute_liu_weisberg_skill(modeled, traj)
        self.assertGreaterEqual(ss_close, 0.90)
        self.assertLessEqual(s_close, 0.10)

    def test_tier1_benchmarks_pass_prd_targets(self) -> None:
        """Verifies Tier 1 SAR segmentation benchmark meets PRD Section 14 targets."""
        t1_results = run_tier1_benchmarks(verbose=False)
        self.assertEqual(len(t1_results), 4)

        metrics_map = {m.metric_name: m for m in t1_results}
        self.assertIn("Mean IoU (mIoU)", metrics_map)
        self.assertIn("F1 Score", metrics_map)
        self.assertIn("False Discovery Rate (FDR)", metrics_map)
        self.assertIn("Lookalike Rejection Rate", metrics_map)

        # Acceptance target assertions
        self.assertTrue(metrics_map["Mean IoU (mIoU)"].passed)
        self.assertGreaterEqual(metrics_map["Mean IoU (mIoU)"].measured_value, 82.5)

        self.assertTrue(metrics_map["F1 Score"].passed)
        self.assertGreaterEqual(metrics_map["F1 Score"].measured_value, 87.0)

        self.assertTrue(metrics_map["False Discovery Rate (FDR)"].passed)
        self.assertLessEqual(metrics_map["False Discovery Rate (FDR)"].measured_value, 12.0)

        self.assertTrue(metrics_map["Lookalike Rejection Rate"].passed)
        self.assertEqual(metrics_map["Lookalike Rejection Rate"].measured_value, 100.0)

    def test_tier3_benchmarks_pass_prd_targets(self) -> None:
        """Verifies Tier 3 drift and backtracking meets PRD targets across >= 3 incidents."""
        t3_results = run_tier3_benchmarks(verbose=False)
        # 3 incidents x 3 metrics = 9 metric records
        self.assertGreaterEqual(len(t3_results), 9)

        cases_found = {m.benchmark_name for m in t3_results}
        self.assertGreaterEqual(len(cases_found), 3)
        self.assertIn("Bombay High 2026", cases_found)
        self.assertIn("Ennore Port 2017", cases_found)
        self.assertIn("Gulf of Kutch 2024", cases_found)

        for m in t3_results:
            self.assertTrue(m.passed, f"Tier 3 metric '{m.metric_name}' failed for case '{m.benchmark_name}'")
            if "Skill Score" in m.metric_name:
                self.assertGreaterEqual(m.measured_value, 0.80)
            elif "Separation Error" in m.metric_name:
                self.assertLessEqual(m.measured_value, 0.15)
            elif "Origin Distance" in m.metric_name:
                self.assertLessEqual(m.measured_value, 1.50)

    def test_tier4_benchmarks_pass_prd_targets(self) -> None:
        """Verifies Tier 4 candidate attribution meets PRD Section 14 targets."""
        t4_results = run_tier4_benchmarks(verbose=False)
        self.assertEqual(len(t4_results), 5)

        metrics_map = {m.metric_name: m for m in t4_results}
        self.assertIn("Top-1 Candidate Accuracy", metrics_map)
        self.assertIn("Top-3 Candidate Accuracy", metrics_map)
        self.assertIn("Dark Gap Flag Rate", metrics_map)
        self.assertIn("Rule 1 Confidence Compliance", metrics_map)
        self.assertIn("Rule 2 Sub-Scores Complete", metrics_map)

        self.assertTrue(metrics_map["Top-1 Candidate Accuracy"].passed)
        self.assertGreaterEqual(metrics_map["Top-1 Candidate Accuracy"].measured_value, 85.0)

        self.assertTrue(metrics_map["Top-3 Candidate Accuracy"].passed)
        self.assertGreaterEqual(metrics_map["Top-3 Candidate Accuracy"].measured_value, 95.0)

        self.assertTrue(metrics_map["Dark Gap Flag Rate"].passed)
        self.assertEqual(metrics_map["Dark Gap Flag Rate"].measured_value, 100.0)

        self.assertTrue(metrics_map["Rule 1 Confidence Compliance"].passed)
        self.assertEqual(metrics_map["Rule 1 Confidence Compliance"].measured_value, 100.0)

        self.assertTrue(metrics_map["Rule 2 Sub-Scores Complete"].passed)
        self.assertEqual(metrics_map["Rule 2 Sub-Scores Complete"].measured_value, 100.0)

    def test_execute_benchmarks_full_suite_summary(self) -> None:
        """Verifies end-to-end execution and aggregate summary generation."""
        metrics, summary = execute_benchmarks(fixture_set="standard", tier_filter="all")
        self.assertIsInstance(summary, SuiteSummary)
        self.assertTrue(summary.overall_passed)
        self.assertEqual(summary.failed_metrics, 0)
        self.assertEqual(summary.total_metrics, len(metrics))
        self.assertGreaterEqual(summary.total_metrics, 18)
        self.assertEqual(summary.pass_rate_pct, 100.0)
        self.assertIn("Tier 1", summary.results_by_tier)
        self.assertIn("Tier 3", summary.results_by_tier)
        self.assertIn("Tier 4", summary.results_by_tier)

    def test_cli_main_invocation_and_json_export(self) -> None:
        """Verifies CLI main function executes with exit code 0 and valid JSON report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_report_path = Path(tmpdir) / "test_report.json"
            exit_code = run_benchmarks_main(
                [
                    "--fixture-set",
                    "standard",
                    "--output-json",
                    str(json_report_path),
                    "--no-color",
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue(json_report_path.exists())

            with open(json_report_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertEqual(data["overall_verdict"], "PASS")
            self.assertEqual(data["summary"]["failed_metrics"], 0)
            self.assertGreaterEqual(data["summary"]["total_metrics"], 18)
            self.assertIn("Tier 1", data["tiers"])
            self.assertIn("Tier 3", data["tiers"])
            self.assertIn("Tier 4", data["tiers"])

    def test_rule6_compliance_in_benchmark_outputs(self) -> None:
        """Verifies benchmark suite outputs strictly contain zero Rule 6 banned determination terms."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_report_path = Path(tmpdir) / "audit_report.json"
            run_benchmarks_main(
                [
                    "--fixture-set",
                    "standard",
                    "--output-json",
                    str(json_report_path),
                    "--no-color",
                ]
            )

            report_text = json_report_path.read_text(encoding="utf-8")
            violations = check_content(report_text, json_report_path)
            self.assertEqual(
                len(violations),
                0,
                f"Rule 6 banned term violations detected in benchmark report: {[v.rule_name for v in violations]}",
            )


if __name__ == "__main__":
    unittest.main()
