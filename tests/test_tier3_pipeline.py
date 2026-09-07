"""Top-level integration test runner for test_tier3_pipeline (TASK-022)."""

from tests.integration.test_tier3_pipeline import TestTier3PipelineIntegration

__all__ = ["TestTier3PipelineIntegration"]

if __name__ == "__main__":
    import unittest

    unittest.main()
