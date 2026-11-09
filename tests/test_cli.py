import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "telemetry_decoder.py"
REAL = ROOT / "fixtures" / "grbalpha_11737297_2025-06-09T18-53-26.bin"
# Second real frame (SatNOGS obs 11738478; identical copy in obs 11738552).
REAL_334 = ROOT / "fixtures" / "grbalpha_11738478_2025-06-09T12-34-55.bin"
# SYNTHETIC: the real fixture with ",V,333," replaced by ",V,412,".
SYNTHETIC = ROOT / "fixtures" / "SYNTHETIC_grbalpha_comd_mcu_10mv_412.bin"


def run_cli(path):
    return subprocess.run(
        [sys.executable, str(CLI), str(path)], capture_output=True, text=True
    )


class CliTests(unittest.TestCase):
    def test_real_fixture(self):
        r = run_cli(REAL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"mcu_10mv": 333, "mcu_volts": 3.33})

    def test_second_real_fixture_334(self):
        r = run_cli(REAL_334)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"mcu_10mv": 334, "mcu_volts": 3.34})

    def test_synthetic_frame_different_value(self):
        r = run_cli(SYNTHETIC)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"mcu_10mv": 412, "mcu_volts": 4.12})

    def test_malformed_truncated_frame(self):
        # The real frame cut to 40 bytes, partway through uptime_since_last.
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "truncated.bin"
            bad.write_bytes(REAL.read_bytes()[:40])
            r = run_cli(bad)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("error:", r.stderr)
        self.assertIn("uptime_since_last", r.stderr)


if __name__ == "__main__":
    unittest.main()
