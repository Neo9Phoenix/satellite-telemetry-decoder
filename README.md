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

## Second real fixture: GRBAlpha COMd beacon, mcu_10mv = 334

| Field | Value |
|---|---|
| File | `fixtures/grbalpha_11738478_2025-06-09T12-34-55.bin` |
| Size | 250 bytes |
| SHA-256 | `3b9a054da68b1fc4ee2c9afcfa0a966f6139fdfc3737e71a188021078bc77234` |
| SatNOGS observation ID | [11738478](https://network.satnogs.org/observations/11738478/) (ground station EIRSAT-1 GS - Dún Chaoin) |
| Source URL | https://s3.eu-central-1.wasabisys.com/satnogs-network/data_obs/2025/6/9/12/11738478/data_11738478_2025-06-09T12-34-55_1 |
| Capture time (UTC) | 2025-06-09T12:34:55Z (frame timestamp from the SatNOGS file name; observation window 2025-06-09T12:31:25Z – 12:37:06Z) |
| Independent copy | [Observation 11738552](https://network.satnogs.org/observations/11738552/) (EIRSAT-1 GS - UCD Physics) received the same transmission. Its file `data_11738552_2025-06-09T12-34-55_1` is byte-identical. |
| Downlink and frame format | Same as the first fixture: 437.025 MHz GFSK 9k6, and a raw AX.25 UI COMd frame with an identical 16-byte header |
| Reference decoder | `satnogs-decoders==1.132.0` gives `"mcu_10mv": 334`, which is 3.34 V |

This fixture is here because its value differs from the first real fixture. Of the 57 real COMd frames compared on 2025-06-09, 55 read 333 and only this transmission read 334.

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

This decoder uses the Python 3.9+ standard library only, with no extra dependencies. It reads a raw GRBAlpha AX.25 COMd frame and prints three fields as JSON:

- **`mcu_10mv`:** the onboard computer supply voltage, counted in 10 mV steps. `mcu_volts` is the same value in volts.
- **`batt`:** the raw `Ve` reading. `batt_mv` is the GRBAlpha battery voltage worked out from it.
- **`temp_cpu_k`:** the CPU core temperature in kelvin. `temp_cpu_c` is the same value in degrees Celsius.

**Units, from the [Cormorant ham radio user guide](https://needronix.eu/products/cormorant/hamradio-user-guide/):**

- **`V`:** the guide calls this the "Microcontroller supply voltage [x10mV]".
- **`Ve`:** an "AUX V" reading. It is raw data from a 12-bit ADC against a 2.5 V reference, taken through a resistor divider whose ratio is specific to each mission. For GRBAlpha the guide gives `Vbat [mV] = Ve * 3,3713`, so `batt_mv = batt × 3.3713`. The calculation uses `Decimal`, so 2421 gives exactly 8161.9173.

The conversion looks plausible: all 57 real COMd frames compared on 2025-06-09 give 8148–8263 mV. That is inside the guide's GRBAlpha 2S1P pack range, which runs from 6500 mV (critical) to 8300 mV (max). However, the guide's own example beacon (`Ve,937`, about 3159 mV) would fall below that range, and the guide does not explain why. Treat `batt_mv` as derived from the documented factor, not as independently confirmed.

- **`T`:** the guide's description is `<CPU_core_temperature[K]>, <power_amplifier_NTC_raw_data>`. The first value is read as `temp_cpu_k`, and `temp_cpu_c = temp_cpu_k − 273.15`. That calculation also uses `Decimal`, so 303 K gives exactly 29.85 °C. The second value is a raw NTC reading, which the CLI does not decode.

The 57 real COMd frames compared on 2025-06-09 give 287–298 K (13.85–24.85 °C), and the first fixture gives 303 K (29.85 °C).

It follows the frame layout from the reference decoder's `comd` type, which cites the Needronix Cormorant ham radio user guide:

- **Bytes 0–15:** a fixed AX.25 UI header, `86a240404040e09e9a728ea4846103f0`. That is CQ-0 ← OM9GRB-0, control `0x03`, PID `0xF0`, with no FCS.
- **Bytes 16 onward:** an ASCII payload, `,COMd,U,<uptime_total>,<uptime_since_last>,R,<reset_count>,V,<mcu_10mv>,Ve,<batt>,T,...`

**What the CLI validates:**

- **Exact header:** the first 16 bytes must equal the header above, byte for byte. Any other header is rejected, including a different SSID byte. For example, the other OM9GRB frames from the same pass end the source address with `0x7f` instead of `0x61`, so the CLI rejects them.
- **Payload start:** the byte after the header must be `,`.
- **Fields through `temp_cpu`:** the next twelve fields are checked in order, and each must end with `,`:
  - `COMd`, `U`, `R`, `V`, `Ve` and `T` must match exactly.
  - `uptime_total`, `uptime_since_last`, `reset_count`, `mcu_10mv`, `batt` and `temp_cpu` must be unsigned decimal integers (ASCII `0-9` only).
- **Not checked:** anything after `temp_cpu`, such as the PA NTC reading, signal levels and counters. It is neither parsed nor validated. There is also no FCS/CRC to check, because SatNOGS stores the frame without one.

### Run

```sh
python3 telemetry_decoder.py fixtures/grbalpha_11737297_2025-06-09T18-53-26.bin
# {"mcu_10mv": 333, "mcu_volts": 3.33, "batt": 2421, "batt_mv": 8161.9173, "temp_cpu_k": 303, "temp_cpu_c": 29.85}
```

If a frame is malformed or unreadable, the decoder prints `error: <file>: <reason>` to stderr and exits with code 1.

### Test

```sh
python3 -m unittest discover -s tests -v
```

There are six tests:

- The first real fixture gives `mcu_10mv` 333 (3.33 V), `batt` 2421 (8161.9173 mV) and `temp_cpu` 303 K (29.85 °C).
- The second real fixture gives `mcu_10mv` 334 (3.34 V), `batt` 2447 (8249.5711 mV) and `temp_cpu` 290 K (16.85 °C).
- The synthetic fixture gives `mcu_10mv` 412 (4.12 V). Its `batt` (2421) and `temp_cpu` (303 K) are unchanged.
- A frame truncated to 40 bytes produces an error naming `uptime_since_last`, a nonzero exit code and nothing on stdout.
- The real frame with `batt` changed to `24x1` produces the error `batt is not an unsigned integer: b'24x1'`, a nonzero exit code and nothing on stdout.
- The real frame with `temp_cpu` changed to `3a3` produces the error `temp_cpu is not an unsigned integer: b'3a3'`, a nonzero exit code and nothing on stdout.

### Known caveats

- The reference decoder gives `batt` and `temp_cpu` as raw integers with no units. The units used here come from the Cormorant guide, not the reference decoder. The PA NTC value (`temp_pa_ntc`) is a raw ADC reading. The guide's Appendix II has an ADC-to-°C lookup table for it, but the CLI does not decode it.
- `csp_mcu_transmitted` decodes as `null` because the payload ends with a trailing comma.
