#!/usr/bin/env python3
"""Replay one archived GRBAlpha pass: CSV of every valid COMd frame + chart.

Reads a pass folder (raw SatNOGS frame files named
data_<obs>_<YYYY-MM-DDTHH-MM-SS>[_suffix], plus pass.json), decodes each frame
with telemetry_decoder.decode_frame (the same function the CLI prints), and
writes:

  * a CSV with one row per valid COMd frame, in reception order: utc,
    source_file, duplicate_of, then every decoder output field. A field the
    frame does not contain (csp_mcu_transmitted) is left empty, never 0.
  * an SVG chart of battery voltage and CPU temperature against UTC. Each
    received frame is one point and points are never joined, so beacons that
    were not received show as gaps. The x axis spans the whole observation
    window.

Frames that are not valid COMd frames (GPS, digipeated traffic, ...) are
skipped and listed on stderr. Standard library only.
"""

import argparse
import csv
import io
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import telemetry_decoder as td

FRAME_NAME = re.compile(
    r"^data_(?P<obs>\d+)_(?P<ts>\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d)(?:_[A-Za-z0-9]+)?$"
)
LEAD_COLUMNS = ("utc", "source_file", "duplicate_of")


class PassError(ValueError):
    """The pass folder cannot be replayed."""


def frame_utc(name: str, obs_id: int) -> datetime:
    m = FRAME_NAME.match(name)
    if not m:
        raise PassError(f"{name}: not a SatNOGS frame file name "
                        "(data_<obs>_<YYYY-MM-DDTHH-MM-SS>[_suffix])")
    if int(m.group("obs")) != obs_id:
        raise PassError(f"{name}: belongs to observation {m.group('obs')}, "
                        f"not {obs_id}")
    return datetime.strptime(m.group("ts"), "%Y-%m-%dT%H-%M-%S").replace(
        tzinfo=timezone.utc)


def parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def format_utc(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_pass(pass_dir: Path):
    """Return (meta, rows, skipped). rows hold every valid frame, sorted."""
    meta = json.loads((pass_dir / "pass.json").read_text(encoding="utf-8"))
    obs_id = meta["satnogs_observation_id"]
    rows, skipped, seen = [], [], {}
    for path in sorted(p for p in pass_dir.iterdir() if p.name.startswith("data_")):
        utc = frame_utc(path.name, obs_id)
        raw = path.read_bytes()
        try:
            output = td.decode_frame(raw)
        except td.FrameError as e:
            skipped.append((path.name, str(e)))
            continue
        rows.append({"utc": utc, "source_file": path.name, "raw": raw,
                     "output": output})
    rows.sort(key=lambda r: (r["utc"], r["source_file"]))
    for r in rows:
        # An identical copy of an earlier frame (same beacon saved twice).
        r["duplicate_of"] = seen.get(r["raw"], "")
        seen.setdefault(r["raw"], r["source_file"])
    if not rows:
        raise PassError(f"{pass_dir}: no valid COMd frames")
    return meta, rows, skipped


def csv_value(v) -> str:
    if v is None:
        return ""  # absent in the frame; never written as 0
    if isinstance(v, float):
        return repr(v)
    return str(v)


def render_csv(rows) -> str:
    fields = list(rows[0]["output"])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(list(LEAD_COLUMNS) + fields)
    for r in rows:
        w.writerow([format_utc(r["utc"]), r["source_file"], r["duplicate_of"]]
                   + [csv_value(r["output"][k]) for k in fields])
    return buf.getvalue()


# ---------------------------------------------------------------- SVG chart

def nice_ticks(lo: float, hi: float, target: int = 4):
    """Clean, evenly spaced tick values covering [lo, hi].

    Returns (ticks, step). The step is 1, 2, 2.5 or 5 times a power of ten,
    and the ticks span at least two steps so a flat series still has room.
    """
    span = hi - lo
    if span <= 0:
        span = abs(hi) * 0.01 or 1.0
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    step = min(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step + 1e-9) * step
    end = math.ceil(hi / step - 1e-9) * step
    if end - start < 2 * step:
        start -= step
        end += step
    n = int(round((end - start) / step))
    return [round(start + i * step, 10) for i in range(n + 1)], step


def tick_decimals(step: float) -> int:
    """Decimal places needed to print every multiple of step exactly."""
    d = 0
    while d < 10 and abs(step * 10 ** d - round(step * 10 ** d)) > 1e-9:
        d += 1
    return d


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_svg(meta, rows) -> str:
    W, H = 760, 560
    left, right = 72, 28
    plot_w = W - left - right
    panels = [
        {"key": "batt_mv", "title": "Battery voltage", "unit": "V",
         "value": lambda o: o["batt_mv"] / 1000, "fmt": "{:.3f}", "top": 142},
        {"key": "temp_cpu_c", "title": "CPU temperature", "unit": "°C",
         "value": lambda o: o["temp_cpu_c"], "fmt": "{:.2f}", "top": 336},
    ]
    panel_h = 140
    t0 = parse_utc(meta["observation_start_utc"])
    t1 = parse_utc(meta["observation_end_utc"])
    total = (t1 - t0).total_seconds()

    def x_of(t):
        return left + (t - t0).total_seconds() / total * plot_w

    n_valid = len(rows)
    n_unique = sum(1 for r in rows if not r["duplicate_of"])
    date = t0.strftime("%Y-%m-%d")
    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
      f'width="{W}" height="{H}" role="img" aria-labelledby="t d" '
      'font-family="system-ui, -apple-system, &quot;Segoe UI&quot;, sans-serif">')
    a(f'<title id="t">GRBAlpha battery voltage and CPU temperature, SatNOGS '
      f'observation {meta["satnogs_observation_id"]}</title>')
    a(f'<desc id="d">Two charts sharing a UTC time axis from '
      f'{format_utc(t0)} to {format_utc(t1)}. {n_valid} valid COMd frames '
      f'({n_unique} distinct beacons) are drawn as unconnected points; gaps '
      'mean no frame was received. Values are in the CSV next to this file.</desc>')
    a("<style>"
      "svg{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;"
      "--grid:#e1e0d9;--axis:#c3c2b7;--series:#2a78d6}"
      "@media (prefers-color-scheme: dark){svg{--surface:#1a1a19;--ink:#f0efec;"
      "--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--series:#3987e5}}"
      ".bg{fill:var(--surface)}.h1{fill:var(--ink);font-size:16px;font-weight:600}"
      ".h2{fill:var(--ink2);font-size:12px}.pt-title{fill:var(--ink);font-size:13px;font-weight:600}"
      ".tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}"
      ".lab{fill:var(--ink2);font-size:11px;font-variant-numeric:tabular-nums}"
      ".grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--axis);stroke-width:1}"
      ".dot{fill:var(--series);stroke:var(--surface);stroke-width:2}"
      ".ring{fill:var(--surface);stroke:var(--series);stroke-width:2}"
      ".hit{fill:transparent}.pt:hover .dot,.pt:hover .ring{stroke-width:3}"
      "</style>")
    a(f'<rect class="bg" width="{W}" height="{H}"/>')
    a(f'<text class="h1" x="{left}" y="30">GRBAlpha telemetry over one SatNOGS pass</text>')
    a(f'<text class="h2" x="{left}" y="50">Observation {meta["satnogs_observation_id"]}'
      f' · station {esc(meta["ground_station"])} · {date} · {n_valid} valid COMd frames'
      f' ({n_unique} distinct beacons)</text>')
    a(f'<text class="h2" x="{left}" y="68">Each point is one received frame. Points are '
      'not joined, so a gap means no frame was received;</text>')
    a(f'<text class="h2" x="{left}" y="84">the time axis spans the whole observation '
      'window.</text>')
    # legend for the two point shapes
    lx = left
    a(f'<circle class="dot" cx="{lx + 5}" cy="106" r="5"/>')
    a(f'<text class="lab" x="{lx + 16}" y="110">frame</text>')
    a(f'<circle class="ring" cx="{lx + 66}" cy="106" r="4"/>')
    a(f'<text class="lab" x="{lx + 77}" y="110">identical copy of the previous frame '
      '(same beacon saved twice)</text>')

    minute0 = t0.replace(second=0) + timedelta(minutes=1)
    minutes = []
    m = minute0
    while m <= t1:
        minutes.append(m)
        m += timedelta(minutes=1)

    for p in panels:
        vals = [p["value"](r["output"]) for r in rows]
        ticks, step = nice_ticks(min(vals), max(vals))
        lo, hi, dec = ticks[0], ticks[-1], tick_decimals(step)
        top, bottom = p["top"], p["top"] + panel_h

        def y_of(v, lo=lo, hi=hi, top=top, bottom=bottom):
            return bottom - (v - lo) / (hi - lo) * (bottom - top)

        a(f'<g class="panel" data-field="{p["key"]}">')
        a(f'<text class="pt-title" x="{left}" y="{top - 10}">{p["title"]} '
          f'<tspan class="h2">({p["unit"]})</tspan></text>')
        for tv in ticks:
            y = y_of(tv)
            cls = "axis" if tv == ticks[0] else "grid"
            a(f'<line class="{cls}" x1="{left}" x2="{left + plot_w}" y1="{y:.1f}" y2="{y:.1f}"/>')
            a(f'<text class="tick" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">'
              f'{tv:.{dec}f}</text>')
        for mm in minutes:
            x = x_of(mm)
            a(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}"/>')
        for r, v in zip(rows, vals):
            x, y = x_of(r["utc"]), y_of(v)
            label = (f'{format_utc(r["utc"])} · {p["fmt"].format(v)} {p["unit"]} · '
                     f'{r["source_file"]}')
            if r["duplicate_of"]:
                label += f' (identical to {r["duplicate_of"]})'
            mark = "ring" if r["duplicate_of"] else "dot"
            a(f'<g class="pt"><title>{esc(label)}</title>'
              f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="12"/>'
              f'<circle class="{mark}" cx="{x:.1f}" cy="{y:.1f}" r="{5 if mark == "dot" else 4}"/></g>')
        # selective direct label: the last received value only
        last = rows[-1]
        lx, ly = x_of(last["utc"]), y_of(vals[-1])
        a(f'<text class="lab" x="{lx + 10:.1f}" y="{ly + 4:.1f}">'
          f'{p["fmt"].format(vals[-1])} {p["unit"]}</text>')
        a("</g>")

    axis_y = panels[-1]["top"] + panel_h
    for mm in minutes:
        x = x_of(mm)
        a(f'<text class="tick" x="{x:.1f}" y="{axis_y + 18}" text-anchor="middle">'
          f'{mm.strftime("%H:%M")}</text>')
    a(f'<text class="lab" x="{left + plot_w / 2:.1f}" y="{axis_y + 40}" '
      f'text-anchor="middle">UTC, {date} (observation window '
      f'{t0.strftime("%H:%M:%S")}–{t1.strftime("%H:%M:%S")})</text>')
    a("</svg>")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Decode every frame of one archived GRBAlpha pass; write a "
        "CSV of the valid COMd frames and an SVG chart of battery voltage and "
        "CPU temperature against UTC.")
    parser.add_argument("pass_dir", type=Path,
                        help="folder with SatNOGS frame files and pass.json")
    parser.add_argument("--csv", type=Path, required=True, help="CSV output path")
    parser.add_argument("--svg", type=Path, required=True, help="SVG output path")
    args = parser.parse_args(argv)

    try:
        meta, rows, skipped = load_pass(args.pass_dir)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    for name, reason in skipped:
        print(f"skipped {name}: {reason}", file=sys.stderr)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.csv.write_text(render_csv(rows), encoding="utf-8")
    args.svg.write_text(render_svg(meta, rows), encoding="utf-8")
    dups = sum(1 for r in rows if r["duplicate_of"])
    print(f"{len(rows)} valid COMd frames ({len(rows) - dups} distinct beacons, "
          f"{dups} identical copies), {len(skipped)} other frames skipped")
    print(f"wrote {args.csv} and {args.svg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
