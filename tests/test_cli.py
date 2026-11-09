import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telemetry_decoder import NTC_TABLE, ntc_to_celsius  # noqa: E402

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
    # temp_pa_c: linear interpolation in the Appendix II NTC table, e.g.
    # 1854 lies between (2048, 25) and (1827, 30): 25 + 194/221*5 = 29.39.
    def test_real_fixture(self):
        self.assert_decodes(REAL, {
            "mcu_10mv": 333, "mcu_volts": 3.33,
            "batt": 2421, "batt_mv": 8161.9173,
            "temp_cpu_k": 303, "temp_cpu_c": 29.85,
            "temp_pa_ntc": 1854, "temp_pa_c": 29.39,
        })

    def test_second_real_fixture_334(self):
        self.assert_decodes(REAL_334, {
            "mcu_10mv": 334, "mcu_volts": 3.34,
            "batt": 2447, "batt_mv": 8249.5711,
            "temp_cpu_k": 290, "temp_cpu_c": 16.85,
            # 2411 between (2503, 15) and (2275, 20): 15 + 92/228*5 = 17.02.
            "temp_pa_ntc": 2411, "temp_pa_c": 17.02,
        })

    def test_synthetic_frame_different_value(self):
        # Only V was changed; the other fields are the real fixture's values.
        self.assert_decodes(SYNTHETIC, {
            "mcu_10mv": 412, "mcu_volts": 4.12,
            "batt": 2421, "batt_mv": 8161.9173,
            "temp_cpu_k": 303, "temp_cpu_c": 29.85,
            "temp_pa_ntc": 1854, "temp_pa_c": 29.39,
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

    def test_pa_ntc_outside_table_gives_null(self):
        # 0 is outside the table (the guide's own example beacon has T,301,0).
        # The frame still decodes; only temp_pa_c is null.
        data = REAL.read_bytes()
        self.assertEqual(data.count(b",T,303,1854,Sig,"), 1)
        r = run_cli_bytes(data.replace(b",T,303,1854,Sig,", b",T,303,0,Sig,"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["temp_pa_ntc"], 0)
        self.assertIsNone(out["temp_pa_c"])
        self.assertEqual(out["temp_cpu_c"], 29.85)

    def test_malformed_non_numeric_temp_pa_ntc(self):
        data = REAL.read_bytes()
        r = run_cli_bytes(data.replace(b",T,303,1854,", b",T,303,18z4,"))
        self.assert_rejected(r, "temp_pa_ntc is not an unsigned integer: b'18z4'")

    def test_missing_sig_label(self):
        data = REAL.read_bytes()
        self.assertEqual(data.count(b",Sig,"), 1)
        r = run_cli_bytes(data.replace(b",Sig,", b",Sgi,"))
        self.assert_rejected(r, "expected signal label b'Sig', got b'Sgi'")


class NtcTableTests(unittest.TestCase):
    def test_every_table_point_is_exact(self):
        for adc, temp in NTC_TABLE:
            self.assertEqual(ntc_to_celsius(adc), float(temp), adc)

    def test_table_shape(self):
        self.assertEqual(len(NTC_TABLE), 42)
        self.assertEqual(NTC_TABLE[0], (4054, -55))
        self.assertEqual(NTC_TABLE[-1], (73, 150))
        adcs = [a for a, _ in NTC_TABLE]
        self.assertEqual(adcs, sorted(adcs, reverse=True))
        self.assertEqual(len(set(adcs)), len(adcs))

    def test_interpolation_between_points(self):
        # 1937 between (2048, 25) and (1827, 30): 25 + 111/221*5 = 27.51.
        self.assertEqual(ntc_to_celsius(1937), 27.51)
        # 78 between (82, 145) and (73, 150): 145 + 4/9*5 = 147.22.
        self.assertEqual(ntc_to_celsius(78), 147.22)

    def test_outside_table_is_none(self):
        for adc in (0, 72, 4055, 4095):
            self.assertIsNone(ntc_to_celsius(adc), adc)


if __name__ == "__main__":
    unittest.main()
