import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telemetry_decoder import (  # noqa: E402
    COUNTER_FIELDS, NTC_TABLE, SIG_FIELDS, _COMD_PREFIX, ntc_to_celsius,
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


def replace_mcu_tail(tail):
    """The real fixture with its final ',MCU,15249184,' replaced by tail."""
    data = REAL.read_bytes()
    old = b",MCU,15249184,"
    assert data.endswith(old)
    return data[:-len(old)] + tail


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
    # Digi..MCU counters follow; csp_mcu_transmitted is None because real
    # frames end ",MCU,<received>," with no transmitted value.
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
            "digipeater_rx_count": 3211, "digipeater_tx_count": 1518149,
            "csp_received": 59966, "csp_transmitted": 4569620,
            "i2c1_received": 19774702, "i2c1_transmitted": 107436,
            "i2c2_received": 106889, "i2c2_transmitted": 41483,
            "rs485_received": 421130, "rs485_transmitted": 15223593,
            "csp_mcu_received": 15249184, "csp_mcu_transmitted": None,
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
            "digipeater_rx_count": 3211, "digipeater_tx_count": 1517402,
            "csp_received": 59966, "csp_transmitted": 4569620,
            "i2c1_received": 19773647, "i2c1_transmitted": 107436,
            "i2c2_received": 106889, "i2c2_transmitted": 41483,
            "rs485_received": 421130, "rs485_transmitted": 15222538,
            "csp_mcu_received": 15248129, "csp_mcu_transmitted": None,
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
            "digipeater_rx_count": 3211, "digipeater_tx_count": 1518149,
            "csp_received": 59966, "csp_transmitted": 4569620,
            "i2c1_received": 19774702, "i2c1_transmitted": 107436,
            "i2c2_received": 106889, "i2c2_transmitted": 41483,
            "rs485_received": 421130, "rs485_transmitted": 15223593,
            "csp_mcu_received": 15249184, "csp_mcu_transmitted": None,
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

    # --- Digi, CSP, I2C1, I2C2, RS485 and MCU counters ---

    def test_final_mcu_value_absent_is_null_not_zero(self):
        # Every real frame ends ",MCU,<received>," with no transmitted value.
        self.assertTrue(REAL.read_bytes().endswith(b",MCU,15249184,"))
        r = run_cli(REAL)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertIn("csp_mcu_transmitted", out)
        self.assertIsNone(out["csp_mcu_transmitted"])
        self.assertIn('"csp_mcu_transmitted": null', r.stdout)

    def test_mcu_tail_guide_form_and_explicit_zeros(self):
        # The guide's example ends ",MCU,835,837" with no trailing comma.
        cases = {
            b",MCU,835,837": (835, 837),
            b",MCU,0,0": (0, 0),
            b",MCU,0,": (0, None),
        }
        for tail, expected in cases.items():
            with self.subTest(tail=tail):
                r = run_cli_bytes(replace_mcu_tail(tail))
                self.assertEqual(r.returncode, 0, r.stderr)
                out = json.loads(r.stdout)
                self.assertEqual(
                    (out["csp_mcu_received"], out["csp_mcu_transmitted"]), expected)

    def test_mcu_tail_malformed_rejected(self):
        cases = {
            b",MCU,835,837,": "got b'837,'",
            b",MCU,835,8x7": "got b'8x7'",
            b",MCU,835,837,9": "got b'837,9'",
            b",MCU,15249184": "csp_mcu_received field was terminated by ','",
            b",MCU,": "csp_mcu_received field was terminated by ','",
        }
        for tail, message in cases.items():
            with self.subTest(tail=tail):
                self.assert_rejected(run_cli_bytes(replace_mcu_tail(tail)), message)

    def test_counters_follow_payload_order(self):
        data = REAL.read_bytes()
        start = data.index(b",Digi,")
        tail = (b",Digi,1,2,CSP,3,4,I2C1,5,6,I2C2,7,8,"
                b"RS485,9,10,MCU,11,12")
        r = run_cli_bytes(data[:start] + tail)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        names = COUNTER_FIELDS[COUNTER_FIELDS.index("digipeater_rx_count"):]
        self.assertEqual([out[k] for k in names], list(range(1, 12)))
        self.assertEqual(out["csp_mcu_transmitted"], 12)
        self.assertEqual(out["ax25_packets_transmitted"], 3708250)

    def test_counter_labels_required(self):
        data = REAL.read_bytes()
        cases = {
            b",CSP,": (b",CSp,", "expected CSP packet counter label b'CSP', got b'CSp'"),
            b",I2C1,": (b",I2C3,", "expected I2C1 packet counter label b'I2C1', got b'I2C3'"),
            b",I2C2,": (b",I2C,", "expected I2C2 packet counter label b'I2C2', got b'I2C'"),
            b",RS485,": (b",RS422,", "expected RS485 packet counter label b'RS485', got b'RS422'"),
            b",MCU,": (b",MCu,", "expected MCU packet counter label b'MCU', got b'MCu'"),
        }
        for old, (new, message) in cases.items():
            with self.subTest(label=old):
                self.assertEqual(data.count(old), 1)
                self.assert_rejected(run_cli_bytes(data.replace(old, new)), message)

    def test_counter_values_must_be_numeric(self):
        data = REAL.read_bytes()
        cases = {
            b",Digi,3211,": (b",Digi,32l1,", "digipeater_rx_count is not an unsigned integer: b'32l1'"),
            b",4569620,I2C1,": (b",-4569620,I2C1,", "csp_transmitted is not an unsigned integer: b'-4569620'"),
            b",I2C2,106889,": (b",I2C2,,", "i2c2_received is not an unsigned integer: b''"),
            b",15223593,MCU,": (b",1.5e7,MCU,", "rs485_transmitted is not an unsigned integer: b'1.5e7'"),
        }
        for old, (new, message) in cases.items():
            with self.subTest(field=old):
                self.assertEqual(data.count(old), 1)
                self.assert_rejected(run_cli_bytes(data.replace(old, new)), message)

    def test_missing_counter_in_group(self):
        # One CSP value: the I2C1 label lands in csp_transmitted's slot.
        data = REAL.read_bytes()
        old = b",CSP,59966,4569620,I2C1,"
        self.assertEqual(data.count(old), 1)
        r = run_cli_bytes(data.replace(old, b",CSP,59966,I2C1,"))
        self.assert_rejected(r, "csp_transmitted is not an unsigned integer: b'I2C1'")

    def test_counter_fields_match_parser_layout(self):
        names = [n for e, n in _COMD_PREFIX if e is None]
        start = names.index("rf_packets_received")
        self.assertEqual(tuple(names[start:]), COUNTER_FIELDS)
        self.assertEqual(_COMD_PREFIX[-2], (b"MCU", "MCU packet counter label"))


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
