"""Run the 21-tool HTTP regression suite in a separate temporary shop."""
import subprocess
import sys
import unittest
from pathlib import Path


class GoldenPathTest(unittest.TestCase):
    def test_offline_shop(self):
        backend = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "tests.flow_checks"], cwd=backend, timeout=120)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
