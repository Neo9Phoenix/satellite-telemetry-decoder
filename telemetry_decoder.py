#!/usr/bin/env python3
"""Decode mcu_10mv from a GRBAlpha AX.25 "COMd" beacon frame.

The frame layout follows the reference decoder (satnogs-decoders 1.132.0,
grbalpha.ksy, type `comd`, which cites the Needronix Cormorant ham radio
user guide):

  bytes 0-15  AX.25 UI header, no FCS: dest "CQ" SSID 0, src "OM9GRB" SSID 0,
              control 0x03, PID 0xF0
  bytes 16-   ASCII payload: ",COMd,U,<uptime_total>,<uptime_since_last>,
              R,<reset_count>,V,<mcu_10mv>,Ve,<batt>,..."
              Each field ends with a comma (0x2C).

mcu_10mv is the onboard computer supply voltage in units of 10 mV.

batt (the "Ve" field) is a raw 12-bit ADC count (2.5 V reference) of an
external voltage behind a resistor divider. For GRBAlpha the Cormorant guide
gives battery voltage as Vbat [mV] = Ve * 3.3713.

temp_cpu (first value after "T") is the CPU core temperature in kelvin;
Celsius = K - 273.15.

temp_pa_ntc (second value after "T") is the raw power-amplifier NTC ADC
reading, converted to degrees C with the guide's Appendix II table.

The six "Sig" values are, in order, sigRxImmediate, sigRxAvg, sigRxMax,
sigBackgroundImmediate, sigBackgroundAvg and sigBackgroundMax. The guide
documents them only as "Radio signal" with no units, so they are raw.

The two "RX" values are RF-side packet counts: packets received and packets
transmitted by the transceiver. The two "Ax" values are the AX.25 packet
counts, received and transmitted.

The remaining counter pairs, each <received>, <transmitted>, are Digi
(digipeater), CSP (RF-side CSP), I2C1, I2C2, RS485 and MCU (CSP interface).
The guide shows the payload ending "MCU,835,837" with no trailing comma.
Real GRBAlpha frames end "MCU,<received>," with the transmitted value
absent; it is then reported as None (JSON null), never as 0.
Source: https://needronix.eu/products/cormorant/hamradio-user-guide/
"""

import argparse
import json
import re
import sys
from decimal import Decimal

AX25_HEADER = bytes.fromhex("86a240404040e09e9a728ea4846103f0")
FIELD_SEP = b","
_UINT = re.compile(rb"[0-9]+")
GRBALPHA_VBAT_MV_PER_COUNT = Decimal("3.3713")
KELVIN_OFFSET = Decimal("273.15")

# Appendix II "NTC temperature conversion table" of the Cormorant guide:
# (ADC value, temperature in degrees C), ADC strictly decreasing.
NTC_TABLE = (
    (4054, -55), (4036, -50), (4011, -45), (3978, -40), (3934, -35),
    (3877, -30), (3804, -25), (3713, -20), (3602, -15), (3469, -10),
    (3313, -5), (3136, 0), (2939, 5), (2726, 10), (2503, 15),
    (2275, 20), (2048, 25), (1827, 30), (1618, 35), (1423, 40),
    (1245, 45), (1084, 50), (941, 55), (815, 60), (705, 65),
    (609, 70), (527, 75), (456, 80), (395, 85), (342, 90),
    (297, 95), (259, 100), (226, 105), (197, 110), (173, 115),
    (152, 120), (134, 125), (118, 130), (104, 135), (93, 140),
    (82, 145), (73, 150),
)

# Every field before the final MCU transmitted value, in payload order. None
# marks a numeric value; a bytes value is a literal label that must match
# exactly. The final value is handled separately in decode_comd.
_COMD_PREFIX = (
    (b"COMd", "frame type"),
    (b"U", "uptime label"),
    (None, "uptime_total"),
    (None, "uptime_since_last"),
    (b"R", "reset label"),
    (None, "reset_count"),
    (b"V", "MCU voltage label"),
    (None, "mcu_10mv"),
    (b"Ve", "battery voltage label"),
    (None, "batt"),
    (b"T", "temperature label"),
    (None, "temp_cpu"),
    (None, "temp_pa_ntc"),
    (b"Sig", "signal label"),
    (None, "sig_rx_immediate"),
    (None, "sig_rx_avg"),
    (None, "sig_rx_max"),
    (None, "sig_background_immediate"),
    (None, "sig_background_avg"),
    (None, "sig_background_max"),
    (b"RX", "RF packet counter label"),
    (None, "rf_packets_received"),
    (None, "rf_packets_transmitted"),
    (b"Ax", "AX.25 packet counter label"),
    (None, "ax25_packets_received"),
    (None, "ax25_packets_transmitted"),
    (b"Digi", "digipeater counter label"),
    (None, "digipeater_rx_count"),
    (None, "digipeater_tx_count"),
    (b"CSP", "CSP packet counter label"),
    (None, "csp_received"),
    (None, "csp_transmitted"),
    (b"I2C1", "I2C1 packet counter label"),
    (None, "i2c1_received"),
    (None, "i2c1_transmitted"),
    (b"I2C2", "I2C2 packet counter label"),
    (None, "i2c2_received"),
    (None, "i2c2_transmitted"),
    (b"RS485", "RS485 packet counter label"),
    (None, "rs485_received"),
    (None, "rs485_transmitted"),
    (b"MCU", "MCU packet counter label"),
    (None, "csp_mcu_received"),
)


class FrameError(ValueError):
    """The input is not a well-formed GRBAlpha COMd frame."""


SIG_FIELDS = (
    "sig_rx_immediate", "sig_rx_avg", "sig_rx_max",
    "sig_background_immediate", "sig_background_avg", "sig_background_max",
)

# Packet counters output as plain integers, in payload order. The final
# csp_mcu_transmitted may be None and is output separately.
COUNTER_FIELDS = (
    "rf_packets_received", "rf_packets_transmitted",
    "ax25_packets_received", "ax25_packets_transmitted",
    "digipeater_rx_count", "digipeater_tx_count",
    "csp_received", "csp_transmitted",
    "i2c1_received", "i2c1_transmitted",
    "i2c2_received", "i2c2_transmitted",
    "rs485_received", "rs485_transmitted",
    "csp_mcu_received",
)


def decode_comd(frame: bytes) -> dict:
    """Return every numeric COMd field, keyed by name.

    csp_mcu_transmitted is None when the frame ends right after
    "MCU,<received>," (as every real GRBAlpha frame does).
    """
    if len(frame) < len(AX25_HEADER):
        raise FrameError(
            f"frame is {len(frame)} bytes; need at least {len(AX25_HEADER)} "
            "for the AX.25 header"
        )
    if frame[: len(AX25_HEADER)] != AX25_HEADER:
        raise FrameError(
            "AX.25 header does not match GRBAlpha COMd "
            f"(expected {AX25_HEADER.hex()}, got {frame[:len(AX25_HEADER)].hex()})"
        )

    payload = frame[len(AX25_HEADER):]
    if not payload.startswith(FIELD_SEP):
        raise FrameError("payload does not start with ','")

    pos = 1
    values = {}
    for expected, name in _COMD_PREFIX:
        end = payload.find(FIELD_SEP, pos)
        if end < 0:
            raise FrameError(f"frame ended before the {name} field was terminated by ','")
        token = payload[pos:end]
        pos = end + 1
        if expected is None:
            if not _UINT.fullmatch(token):
                raise FrameError(f"{name} is not an unsigned integer: {token!r}")
            values[name] = int(token)
        elif token != expected:
            raise FrameError(f"expected {name} {expected!r}, got {token!r}")

    # The final value has no terminating comma: the rest of the payload is
    # either empty (value absent) or exactly one unsigned integer.
    rest = payload[pos:]
    if rest == b"":
        values["csp_mcu_transmitted"] = None
    elif _UINT.fullmatch(rest):
        values["csp_mcu_transmitted"] = int(rest)
    else:
        raise FrameError(
            "csp_mcu_transmitted must be absent or an unsigned integer ending "
            f"the frame, got {rest!r}"
        )
    return values


def to_volts(mcu_10mv: int) -> float:
    # Decimal avoids binary rounding noise, e.g. 333 -> 3.33 exactly.
    return float(Decimal(mcu_10mv) / 100)


def batt_to_mv(batt: int) -> float:
    # GRBAlpha-specific divider factor from the Cormorant guide.
    return float(Decimal(batt) * GRBALPHA_VBAT_MV_PER_COUNT)


def kelvin_to_celsius(kelvin: int) -> float:
    # Decimal keeps e.g. 303 -> 29.85 exact.
    return float(Decimal(kelvin) - KELVIN_OFFSET)


def ntc_to_celsius(adc: int):
    """Convert a PA NTC ADC reading to degrees C via the Appendix II table.

    Linear interpolation between table points (the guide states no rule),
    rounded to 0.01 C. Returns None outside the table (above 4054 or below
    73), e.g. the guide's own example reading of 0.
    """
    hi_adc, lo_adc = NTC_TABLE[0][0], NTC_TABLE[-1][0]
    if adc > hi_adc or adc < lo_adc:
        return None
    for (a0, t0), (a1, t1) in zip(NTC_TABLE, NTC_TABLE[1:]):
        if a1 <= adc <= a0:
            frac = Decimal(a0 - adc) / Decimal(a0 - a1)
            temp = Decimal(t0) + frac * Decimal(t1 - t0)
            return float(temp.quantize(Decimal("0.01")))
    raise AssertionError("unreachable: NTC_TABLE covers the checked range")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Print mcu_10mv (and volts), batt (and mV), temp_cpu "
        "(K and degrees C), temp_pa_ntc (raw and degrees C), the six raw "
        "Sig signal values and all packet counters from a raw "
        "GRBAlpha AX.25 COMd frame as JSON."
    )
    parser.add_argument("frame_file", help="path to a raw binary frame (AX.25 without FCS)")
    args = parser.parse_args(argv)

    try:
        with open(args.frame_file, "rb") as f:
            frame = f.read()
        values = decode_comd(frame)
    except (OSError, FrameError) as e:
        print(f"error: {args.frame_file}: {e}", file=sys.stderr)
        return 1

    print(json.dumps({
        "mcu_10mv": values["mcu_10mv"],
        "mcu_volts": to_volts(values["mcu_10mv"]),
        "batt": values["batt"],
        "batt_mv": batt_to_mv(values["batt"]),
        "temp_cpu_k": values["temp_cpu"],
        "temp_cpu_c": kelvin_to_celsius(values["temp_cpu"]),
        "temp_pa_ntc": values["temp_pa_ntc"],
        "temp_pa_c": ntc_to_celsius(values["temp_pa_ntc"]),
        **{name: values[name] for name in SIG_FIELDS},
        **{name: values[name] for name in COUNTER_FIELDS},
        "csp_mcu_transmitted": values["csp_mcu_transmitted"],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
