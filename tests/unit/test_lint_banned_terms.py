"""Unit tests for AEGIS-Marine Rule 6 Banned Term Linter."""

import unittest
from pathlib import Path
from scripts.lint_banned_terms import check_content, run_self_tests


class TestBannedTermsLinter(unittest.TestCase):
    def test_self_test_suite(self) -> None:
        """Ensure the built-in self-tests pass."""
        self.assertTrue(run_self_tests())

    def test_approved_terminology_passes(self) -> None:
        """Ensure approved objective terminology produces 0 violations."""
        clean_text = """
        The candidate suspect vessel IMO 9123456 has the highest attribution score.
        It is the most correlated vessel within the estimated origin cloud.
        The slick orientation aligns with the potential source vessel heading.
        """
        violations = check_content(clean_text, Path("test_approved.py"))
        self.assertEqual(len(violations), 0)

    def test_banned_terms_fail(self) -> None:
        """Ensure each banned term is accurately detected."""
        v1 = check_content("The responsible vessel fled the scene.", Path("test.py"))
        self.assertEqual(len(v1), 1)
        self.assertEqual(v1[0].rule_name, "responsible vessel")

        v2 = check_content("The court found the captain guilty.", Path("test.py"))
        self.assertEqual(len(v2), 1)
        self.assertEqual(v2[0].rule_name, "guilty")

        v3 = check_content("We confirmed the culprit via AIS.", Path("test.py"))
        self.assertEqual(len(v3), 1)
        self.assertEqual(v3[0].rule_name, "confirmed the culprit")

        v4 = check_content("It is proven that the spill happened at noon.", Path("test.py"))
        self.assertEqual(len(v4), 1)
        self.assertEqual(v4[0].rule_name, "proven")

        v5 = check_content("Coast guard intercepted the polluter.", Path("test.py"))
        self.assertEqual(len(v5), 1)
        self.assertEqual(v5[0].rule_name, "polluter (as determination)")


if __name__ == "__main__":
    unittest.main()
