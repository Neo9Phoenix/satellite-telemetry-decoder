# Satellite Telemetry Decoder

## Reference fixture: GRBAlpha COMd beacon

| Field | Value |
|---|---|
| File | `fixtures/grbalpha_11737297_2025-06-09T18-53-26.bin` |
| Size | 249 bytes |
| SHA-256 | `f49b3170f040ad15e04b128a0509e20bb2242267a8fbcd00bd88bea194d70156` |
| Satellite | GRBAlpha (NORAD 47959), callsign OM9GRB |
| SatNOGS observation ID | [11737297](https://network.satnogs.org/observations/11737297/) (ground station VU2JEK_Nitin) |
| Source URL | https://s3.eu-central-1.wasabisys.com/satnogs-network/data_obs/2025/6/9/18/11737297/data_11737297_2025-06-09T18-53-26 |
| Capture time (UTC) | 2025-06-09T18:53:26Z (frame timestamp from the SatNOGS file name; observation window 2025-06-09T18:52:08Z – 18:58:18Z) |
| Downlink | 437.025 MHz, "Mode U - GFSK9k6 - AX.25 G3RUH", 9600 baud |
| Frame format | Raw AX.25 UI frame without the FCS/CRC (OM9GRB → CQ, control `0x03`, PID `0xF0`). The payload is GRBAlpha's comma-separated ASCII "COMd" comms housekeeping beacon. |
| Reference decoder | `satnogs-decoders==1.132.0`, decoder `grbalpha` |

Metadata comes from the public SatNOGS Network API:
`https://network.satnogs.org/api/observations/11737297/?format=json`

### Synthetic fixture (not real satellite data)

`fixtures/SYNTHETIC_grbalpha_comd_mcu_10mv_412.bin` is the real fixture with `,V,333,` replaced by `,V,412,`. Every other byte is unchanged, and it is 249 bytes.
SHA-256: `ca9bcb2062d4a501ae86c951434e732eda16b76edf560346d908a91c0e111b15`. The reference decoder reads it as `"mcu_10mv": 412`.

### Reference decoder setup

All commands run from the project folder. `.venv/` is git-ignored.

```sh
python3 -m venv .venv
.venv/bin/pip install satnogs-decoders==1.132.0
```

### Verify and decode with the reference decoder

```sh
shasum -a 256 fixtures/grbalpha_11737297_2025-06-09T18-53-26.bin
.venv/bin/decode_frame grbalpha fixtures/grbalpha_11737297_2025-06-09T18-53-26.bin
```

Expected output includes `"mcu_10mv": 333`, which is 3.33 V (onboard computer supply; the field counts in 10 mV steps).

## Our decoder: `telemetry_decoder.py`

This decoder uses the Python 3.9+ standard library only, with no extra dependencies. It reads a raw GRBAlpha AX.25 COMd frame and prints `mcu_10mv` and its value in volts as JSON.

It follows the frame layout from the reference decoder's `comd` type, which cites the Needronix Cormorant ham radio user guide:

- **Bytes 0–15:** a fixed AX.25 UI header, `86a240404040e09e9a728ea4846103f0`. That is CQ-0 ← OM9GRB-0, control `0x03`, PID `0xF0`, with no FCS.
- **Bytes 16 onward:** an ASCII payload, `,COMd,U,<uptime_total>,<uptime_since_last>,R,<reset_count>,V,<mcu_10mv>,Ve,...`

**What the CLI validates:**

- **Exact header:** the first 16 bytes must equal the header above, byte for byte. Any other header is rejected, including a different SSID byte. For example, the other OM9GRB frames from the same pass end the source address with `0x7f` instead of `0x61`, so the CLI rejects them.
- **Payload start:** the byte after the header must be `,`.
- **Fields through `Ve`:** the next nine fields are checked in order, and each must end with `,`:
  - `COMd`, `U`, `R`, `V` and `Ve` must match exactly.
  - `uptime_total`, `uptime_since_last`, `reset_count` and `mcu_10mv` must be unsigned decimal integers (ASCII `0-9` only).
- **Not checked:** anything after the `Ve,` label, such as `batt`, temperatures and counters. It is neither parsed nor validated. There is also no FCS/CRC to check, because SatNOGS stores the frame without one.

### Run

```sh
python3 telemetry_decoder.py fixtures/grbalpha_11737297_2025-06-09T18-53-26.bin
# {"mcu_10mv": 333, "mcu_volts": 3.33}
```

If a frame is malformed or unreadable, the decoder prints `error: <file>: <reason>` to stderr and exits with code 1.

### Test

```sh
python3 -m unittest discover -s tests -v
```

There are three tests:

- The real fixture gives 333, which is 3.33 V.
- The synthetic fixture gives 412, which is 4.12 V.
- A frame truncated to 40 bytes produces an error naming `uptime_since_last`, a nonzero exit code and nothing on stdout.

### Known caveats

- The decoder does not state units for `batt` (2421) or `temp_cpu` (303). Check GRBAlpha documentation before interpreting them.
- `csp_mcu_transmitted` decodes as `null` because the payload ends with a trailing comma.
