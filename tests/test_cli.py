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


def run_cli_bytes(data):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "frame.bin"
        p.write_bytes(data)
        return run_cli(p)


class CliTests(unittest.TestCase):
    def assert_decodes(self, path, expected):
        r = run_cli(path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), expected)

    def assert_rejected(self, r, field):
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("error:", r.stderr)
        self.assertIn(field, r.stderr)

    # batt_mv = batt * 3.3713 (GRBAlpha factor from the Cormorant guide).
    # temp_cpu_c = temp_cpu_k - 273.15 (guide gives temp_cpu in kelvin).
    def test_real_fixture(self):
        self.assert_decodes(REAL, {
            "mcu_10mv": 333, "mcu_volts": 3.33,
            "batt": 2421, "batt_mv": 8161.9173,
            "temp_cpu_k": 303, "temp_cpu_c": 29.85,
        })

    def test_second_real_fixture_334(self):
        self.assert_decodes(REAL_334, {
            "mcu_10mv": 334, "mcu_volts": 3.34,
            "batt": 2447, "batt_mv": 8249.5711,
            "temp_cpu_k": 290, "temp_cpu_c": 16.85,
        })

    def test_synthetic_frame_different_value(self):
        # Only V was changed; batt and temp_cpu are the real fixture's values.
        self.assert_decodes(SYNTHETIC, {
            "mcu_10mv": 412, "mcu_volts": 4.12,
            "batt": 2421, "batt_mv": 8161.9173,
            "temp_cpu_k": 303, "temp_cpu_c": 29.85,
        })

    def test_malformed_truncated_frame(self):
        # The real frame cut to 40 bytes, partway through uptime_since_last.
        r = run_cli_bytes(REAL.read_bytes()[:40])
        self.assert_rejected(r, "uptime_since_last")

    def test_malformed_non_numeric_batt(self):
        data = REAL.read_bytes()
        self.assertEqual(data.count(b",Ve,2421,"), 1)
        r = run_cli_bytes(data.replace(b",Ve,2421,", b",Ve,24x1,"))
        self.assert_rejected(r, "batt is not an unsigned integer: b'24x1'")

    def test_malformed_non_numeric_temp_cpu(self):
        data = REAL.read_bytes()
        self.assertEqual(data.count(b",T,303,"), 1)
        r = run_cli_bytes(data.replace(b",T,303,", b",T,3a3,"))
        self.assert_rejected(r, "temp_cpu is not an unsigned integer: b'3a3'")


if __name__ == "__main__":
    unittest.main()
