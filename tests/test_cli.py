import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telemetry_decoder import (  # noqa: E402
    NTC_TABLE, SIG_FIELDS, _COMD_PREFIX, ntc_to_celsius,
)

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
    # sig_*: raw, in payload order after "Sig" (the guide gives no units).
    # rf_packets_*: the two RX counters (received, transmitted).
    # ax25_packets_*: the two Ax counters (received, transmitted).
    def test_real_fixture(self):
        self.assert_decodes(REAL, {
            "mcu_10mv": 333, "mcu_volts": 3.33,
            "batt": 2421, "batt_mv": 8161.9173,
            "temp_cpu_k": 303, "temp_cpu_c": 29.85,
            "temp_pa_ntc": 1854, "temp_pa_c": 29.39,
            "sig_rx_immediate": 1917, "sig_rx_avg": 1751, "sig_rx_max": 1751,
            "sig_background_immediate": 1003, "sig_background_avg": 998,
            "sig_background_max": 1022,
            "rf_packets_received": 63572, "rf_packets_transmitted": 8277857,
            "ax25_packets_received": 3211, "ax25_packets_transmitted": 3708250,
        })

    def test_second_real_fixture_334(self):
        self.assert_decodes(REAL_334, {
            "mcu_10mv": 334, "mcu_volts": 3.34,
            "batt": 2447, "batt_mv": 8249.5711,
            "temp_cpu_k": 290, "temp_cpu_c": 16.85,
            # 2411 between (2503, 15) and (2275, 20): 15 + 92/228*5 = 17.02.
            "temp_pa_ntc": 2411, "temp_pa_c": 17.02,
            "sig_rx_immediate": 1917, "sig_rx_avg": 1751, "sig_rx_max": 1751,
            "sig_background_immediate": 1219, "sig_background_avg": 1193,
            "sig_background_max": 1194,
            "rf_packets_received": 63572, "rf_packets_transmitted": 8276732,
            "ax25_packets_received": 3211, "ax25_packets_transmitted": 3707125,
        })

    def test_synthetic_frame_different_value(self):
        # Only V was changed; the other fields are the real fixture's values.
        self.assert_decodes(SYNTHETIC, {
            "mcu_10mv": 412, "mcu_volts": 4.12,
            "batt": 2421, "batt_mv": 8161.9173,
            "temp_cpu_k": 303, "temp_cpu_c": 29.85,
            "temp_pa_ntc": 1854, "temp_pa_c": 29.39,
            "sig_rx_immediate": 1917, "sig_rx_avg": 1751, "sig_rx_max": 1751,
            "sig_background_immediate": 1003, "sig_background_avg": 998,
            "sig_background_max": 1022,
            "rf_packets_received": 63572, "rf_packets_transmitted": 8277857,
            "ax25_packets_received": 3211, "ax25_packets_transmitted": 3708250,
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

    def test_sig_values_follow_payload_order(self):
        # Six distinct values make any swapped field visible.
        data = REAL.read_bytes()
        old = b",Sig,1917,1751,1751,1003,998,1022,RX,"
        self.assertEqual(data.count(old), 1)
        r = run_cli_bytes(data.replace(old, b",Sig,1,22,333,4444,5,66,RX,"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([out[k] for k in SIG_FIELDS], [1, 22, 333, 4444, 5, 66])

    def test_malformed_non_numeric_sig_value(self):
        data = REAL.read_bytes()
        r = run_cli_bytes(data.replace(b",1003,998,1022,RX,", b",1003,9o8,1022,RX,"))
        self.assert_rejected(
            r, "sig_background_avg is not an unsigned integer: b'9o8'")

    def test_malformed_missing_sig_value(self):
        # Only five values: the RX label lands in the sixth value's slot.
        data = REAL.read_bytes()
        r = run_cli_bytes(data.replace(b",1003,998,1022,RX,", b",1003,998,RX,"))
        self.assert_rejected(
            r, "sig_background_max is not an unsigned integer: b'RX'")

    def test_missing_rx_label(self):
        data = REAL.read_bytes()
        self.assertEqual(data.count(b",RX,"), 1)
        r = run_cli_bytes(data.replace(b",RX,", b",XR,"))
        self.assert_rejected(
            r, "expected RF packet counter label b'RX', got b'XR'")

    def test_rx_counters_follow_payload_order(self):
        data = REAL.read_bytes()
        old = b",RX,63572,8277857,Ax,"
        self.assertEqual(data.count(old), 1)
        r = run_cli_bytes(data.replace(old, b",RX,12,3456,Ax,"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(
            (out["rf_packets_received"], out["rf_packets_transmitted"]), (12, 3456))

    def test_malformed_non_numeric_rx_counter(self):
        data = REAL.read_bytes()
        r = run_cli_bytes(data.replace(b",RX,63572,", b",RX,635-2,"))
        self.assert_rejected(
            r, "rf_packets_received is not an unsigned integer: b'635-2'")

    def test_malformed_missing_rx_counter(self):
        # Only one counter: the Ax label lands in the second counter's slot.
        data = REAL.read_bytes()
        r = run_cli_bytes(data.replace(b",RX,63572,8277857,Ax,", b",RX,63572,Ax,"))
        self.assert_rejected(
            r, "rf_packets_transmitted is not an unsigned integer: b'Ax'")

    def test_missing_ax_label(self):
        data = REAL.read_bytes()
        self.assertEqual(data.count(b",Ax,"), 1)
        r = run_cli_bytes(data.replace(b",Ax,", b",AX,"))
        self.assert_rejected(
            r, "expected AX.25 packet counter label b'Ax', got b'AX'")

    def test_ax_counters_follow_payload_order(self):
        data = REAL.read_bytes()
        old = b",Ax,3211,3708250,Digi,"
        self.assertEqual(data.count(old), 1)
        r = run_cli_bytes(data.replace(old, b",Ax,7,89,Digi,"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(
            (out["ax25_packets_received"], out["ax25_packets_transmitted"]), (7, 89))
        # The RX counters just before Ax are untouched.
        self.assertEqual(out["rf_packets_transmitted"], 8277857)

    def test_malformed_non_numeric_ax_counter(self):
        data = REAL.read_bytes()
        r = run_cli_bytes(data.replace(b",3708250,Digi,", b",37O8250,Digi,"))
        self.assert_rejected(
            r, "ax25_packets_transmitted is not an unsigned integer: b'37O8250'")

    def test_malformed_missing_ax_counter(self):
        # Only one counter: the Digi label lands in the second counter's slot.
        data = REAL.read_bytes()
        r = run_cli_bytes(data.replace(b",Ax,3211,3708250,Digi,", b",Ax,3211,Digi,"))
        self.assert_rejected(
            r, "ax25_packets_transmitted is not an unsigned integer: b'Digi'")

    def test_missing_digi_label(self):
        data = REAL.read_bytes()
        self.assertEqual(data.count(b",Digi,"), 1)
        r = run_cli_bytes(data.replace(b",Digi,", b",Digl,"))
        self.assert_rejected(
            r, "expected digipeater counter label b'Digi', got b'Digl'")

    def test_sig_fields_match_parser_layout(self):
        names = [n for _, n in _COMD_PREFIX]
        i = names.index("signal label")
        self.assertEqual(tuple(names[i + 1:i + 7]), SIG_FIELDS)
        self.assertEqual(names[i + 7], "RF packet counter label")


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
