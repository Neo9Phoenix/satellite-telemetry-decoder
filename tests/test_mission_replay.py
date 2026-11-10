import csv
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import telemetry_decoder as td  # noqa: E402

DECODER_CLI = ROOT / "telemetry_decoder.py"
REPLAY_CLI = ROOT / "mission_replay.py"
PASS_DIR = ROOT / "fixtures" / "pass_11738469"
CSV_OUT = ROOT / "replay" / "grbalpha_11738469.csv"
SVG_OUT = ROOT / "replay" / "grbalpha_11738469.svg"
LEAD = ["utc", "source_file", "duplicate_of"]


def frame_files():
    return sorted(p for p in PASS_DIR.iterdir() if p.name.startswith("data_"))


def valid_frame_names():
    """Frames the decoder itself accepts, found without the replay code."""
    names = []
    for p in frame_files():
        try:
            td.decode_comd(p.read_bytes())
        except td.FrameError:
            continue
        names.append(p.name)
    return names


def read_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def expected_cell(value):
    """How a decoder JSON value must appear in the CSV."""
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def run_replay(pass_dir, out_dir):
    out = Path(out_dir)
    return subprocess.run(
        [sys.executable, str(REPLAY_CLI), str(pass_dir),
         "--csv", str(out / "pass.csv"), "--svg", str(out / "pass.svg")],
        capture_output=True, text=True)


class ReplayCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = run_replay(PASS_DIR, cls.tmp.name)
        out = Path(cls.tmp.name)
        cls.csv_text = (out / "pass.csv").read_text(encoding="utf-8")
        cls.svg_text = (out / "pass.svg").read_text(encoding="utf-8")
        cls.rows = read_csv(cls.csv_text)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_replay_succeeds(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertIn("7 valid COMd frames (4 distinct beacons, 3 identical copies), "
                      "10 other frames skipped", self.result.stdout)

    def test_one_row_per_valid_frame(self):
        valid = valid_frame_names()
        self.assertEqual(len(frame_files()), 17)
        self.assertEqual(len(valid), 7)
        self.assertEqual(len(self.rows), len(valid))
        self.assertEqual(sorted(r["source_file"] for r in self.rows), valid)
        # Every other frame is reported as skipped, with a reason.
        skipped = re.findall(r"^skipped (\S+): ", self.result.stderr, re.M)
        self.assertEqual(sorted(skipped + valid), [p.name for p in frame_files()])

    def test_each_row_matches_decoder_cli_output(self):
        for row in self.rows:
            with self.subTest(frame=row["source_file"]):
                r = subprocess.run(
                    [sys.executable, str(DECODER_CLI), str(PASS_DIR / row["source_file"])],
                    capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                cli = json.loads(r.stdout)
                # Same fields, same order, same values.
                self.assertEqual(list(row)[len(LEAD):], list(cli))
                for key, value in cli.items():
                    self.assertEqual(row[key], expected_cell(value), key)

    def test_missing_value_is_empty_not_zero(self):
        for row in self.rows:
            self.assertEqual(row["csp_mcu_transmitted"], "")

    def test_utc_comes_from_file_name_and_rows_are_in_order(self):
        meta = json.loads((PASS_DIR / "pass.json").read_text(encoding="utf-8"))
        start = meta["observation_start_utc"]
        end = meta["observation_end_utc"]
        times = []
        for row in self.rows:
            stamp = re.search(r"_(\d{4}-\d\d-\d\dT\d\d)-(\d\d)-(\d\d)",
                              row["source_file"]).groups()
            self.assertEqual(row["utc"], f"{stamp[0]}:{stamp[1]}:{stamp[2]}Z")
            self.assertTrue(start <= row["utc"] <= end, row["utc"])
            times.append(row["utc"])
        self.assertEqual(times, sorted(times))

    def test_identical_copies_are_flagged(self):
        seen = {}
        flagged = 0
        for row in self.rows:
            data = (PASS_DIR / row["source_file"]).read_bytes()
            if row["duplicate_of"]:
                flagged += 1
                self.assertIn(row["duplicate_of"], seen.values())
                self.assertEqual(data, (PASS_DIR / row["duplicate_of"]).read_bytes())
            else:
                self.assertNotIn(data, seen)
                seen[data] = row["source_file"]
        self.assertEqual(flagged, 3)

    def test_committed_outputs_are_reproducible(self):
        self.assertEqual(CSV_OUT.read_text(encoding="utf-8"), self.csv_text)
        self.assertEqual(SVG_OUT.read_text(encoding="utf-8"), self.svg_text)

    def test_svg_plots_every_row_as_an_unjoined_point(self):
        panels = re.findall(r'<g class="panel" data-field="(\w+)">(.*?)</g>\n?(?=<g class="panel"|<text)',
                            self.svg_text, re.S)
        self.assertEqual([name for name, _ in panels], ["batt_mv", "temp_cpu_c"])
        for name, body in panels:
            with self.subTest(panel=name):
                self.assertEqual(body.count('<g class="pt">'), len(self.rows))
                self.assertEqual(body.count('class="dot"'), 4)
                self.assertEqual(body.count('class="ring"'), 3)
        # No line or path joins the samples.
        self.assertNotIn("<polyline", self.svg_text)
        self.assertNotIn("<path", self.svg_text)

    def test_svg_point_positions_follow_utc_and_values(self):
        # x grows with time; y order follows the battery values in the CSV.
        batt = re.search(r'data-field="batt_mv">(.*?)</g>\n<g class="panel"',
                         self.svg_text, re.S).group(1)
        marks = re.findall(r'class="(?:dot|ring)" cx="([\d.]+)" cy="([\d.]+)"', batt)
        xs = [float(x) for x, _ in marks]
        ys = [float(y) for _, y in marks]
        self.assertEqual(xs, sorted(xs))
        volts = [float(r["batt_mv"]) for r in self.rows]
        for i in range(len(volts)):
            for j in range(len(volts)):
                if volts[i] > volts[j]:
                    self.assertLess(ys[i], ys[j])


class ReplayErrorTests(unittest.TestCase):
    def make_pass(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name) / "pass"
        d.mkdir()
        (d / "pass.json").write_bytes((PASS_DIR / "pass.json").read_bytes())
        for name, data in files.items():
            (d / name).write_bytes(data)
        return d, tmp.name

    def test_badly_named_frame_is_an_error(self):
        good = (PASS_DIR / "data_11738469_2025-06-09T11-05-23").read_bytes()
        d, out = self.make_pass({"data_11738469_2025-06-09_11-05-23": good})
        r = run_replay(d, out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a SatNOGS frame file name", r.stderr)

    def test_frame_from_another_observation_is_an_error(self):
        good = (PASS_DIR / "data_11738469_2025-06-09T11-05-23").read_bytes()
        d, out = self.make_pass({"data_11738478_2025-06-09T11-05-23": good})
        r = run_replay(d, out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("belongs to observation 11738478, not 11738469", r.stderr)

    def test_pass_without_valid_frames_is_an_error(self):
        gps = (PASS_DIR / "data_11738469_2025-06-09T11-04-55").read_bytes()
        d, out = self.make_pass({"data_11738469_2025-06-09T11-04-55": gps})
        r = run_replay(d, out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no valid COMd frames", r.stderr)


if __name__ == "__main__":
    unittest.main()
