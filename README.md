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

This decoder uses the Python 3.9+ standard library only, with no extra dependencies. It reads a raw GRBAlpha AX.25 COMd frame and prints these fields as JSON:

- **`uptime_total` and `uptime_since_last`:** total uptime and uptime since the last reset, in seconds.
- **`reset_count`:** the number of resets from any source.
- **`mcu_10mv`:** the onboard computer supply voltage, counted in 10 mV steps. `mcu_volts` is the same value in volts.
- **`batt`:** the raw `Ve` reading. `batt_mv` is the GRBAlpha battery voltage worked out from it.
- **`temp_cpu_k`:** the CPU core temperature in kelvin. `temp_cpu_c` is the same value in degrees Celsius.
- **`temp_pa_ntc`:** the raw power-amplifier NTC reading. `temp_pa_c` is that reading converted to degrees Celsius.
- **Six raw radio signal values:** `sig_rx_immediate`, `sig_rx_avg`, `sig_rx_max`, `sig_background_immediate`, `sig_background_avg` and `sig_background_max`. They have no units.
- **`rf_packets_received` and `rf_packets_transmitted`:** the two RX packet counters, as plain packet counts.
- **`ax25_packets_received` and `ax25_packets_transmitted`:** the two Ax packet counters, as plain packet counts.
- **The remaining counter pairs,** each a received and a transmitted count:
  - `digipeater_rx_count` and `digipeater_tx_count`
  - `csp_received` and `csp_transmitted`
  - `i2c1_received` and `i2c1_transmitted`
  - `i2c2_received` and `i2c2_transmitted`
  - `rs485_received` and `rs485_transmitted`
  - `csp_mcu_received` and `csp_mcu_transmitted`. The transmitted value can be `null`; see below.

**Units, from the [Cormorant ham radio user guide](https://needronix.eu/products/cormorant/hamradio-user-guide/):**

- **`U`:** the guide gives `<total_uptime[s]>, <uptime_since_last_reset[s]>`, so both values are seconds and are output as-is.
- **`R`:** the guide calls this the "Reset counter" and says "This includes any reset source - Brown-out, Watchdog, SW etc."

  The real frames are consistent with this. In all 57 archive frames, `uptime_total − uptime_since_last` is the same 112208738 s, as it should be when both counters advance together, and `reset_count` is 346. The CLI does not check any relationship between these values.

- **`V`:** the guide calls this the "Microcontroller supply voltage [x10mV]".
- **`Ve`:** an "AUX V" reading. It is raw data from a 12-bit ADC against a 2.5 V reference, taken through a resistor divider whose ratio is specific to each mission. For GRBAlpha the guide gives `Vbat [mV] = Ve * 3,3713`, so `batt_mv = batt × 3.3713`. The calculation uses `Decimal`, so 2421 gives exactly 8161.9173.

The conversion looks plausible: all 57 real COMd frames compared on 2025-06-09 give 8148–8263 mV. That is inside the guide's GRBAlpha 2S1P pack range, which runs from 6500 mV (critical) to 8300 mV (max). However, the guide's own example beacon (`Ve,937`, about 3159 mV) would fall below that range, and the guide does not explain why. Treat `batt_mv` as derived from the documented factor, not as independently confirmed.

- **`T`:** the guide's description is `<CPU_core_temperature[K]>, <power_amplifier_NTC_raw_data>`. The first value is read as `temp_cpu_k`, and `temp_cpu_c = temp_cpu_k − 273.15`. That calculation also uses `Decimal`, so 303 K gives exactly 29.85 °C. The second value is the raw PA NTC reading, `temp_pa_ntc`.

The 57 real COMd frames compared on 2025-06-09 give 287–298 K (13.85–24.85 °C), and the first fixture gives 303 K (29.85 °C).

- **PA NTC (Appendix II):** `temp_pa_c` comes from the guide's "9. Appendix II. - NTC temperature conversion table". That table has 42 points, running from ADC 4054 = −55 °C to ADC 73 = 150 °C in 5 °C steps, and it is copied into `NTC_TABLE` in `telemetry_decoder.py`. The copy was checked against a parse of the live page on 2026-11-09, and all 42 points matched. The guide gives no interpolation rule, so the CLI makes three choices of its own:
  - **Exact table point:** the table value is used.
  - **Between two points:** the CLI interpolates linearly between the two neighbouring points and rounds to 0.01 °C. For example, 1854 gives 25 + 194/221 × 5 = 29.39 °C.
  - **Outside the table** (above 4054 or below 73): `temp_pa_c` is `null`. The frame still decodes, because the guide's own example beacon has a PA reading of `0`.

  A cross-check supports the conversion: on all 57 real COMd frames, `temp_pa_c` stays within −1.41 to +0.31 °C of the CPU temperature, which is an independent sensor. The two fixtures give PA 29.39 °C against CPU 29.85 °C, and PA 17.02 °C against CPU 16.85 °C.

- **`Sig`:** the guide lists the six values as `<sigRxImmediate>, <sigiRxAvg>, <sigRxMax>, <sigBackgroundImmediate>, <sigBackgroundAvg>, <sigBackgroundMax>`, which is the same order the reference decoder uses. It describes them only as "Radio signal", with empty unit cells. The page mentions no RSSI, dBm or scaling for them; dBm appears only in the 1 W transmit power. So the CLI outputs them as raw integers and does not convert them to dBm.

  Observations from the 57 real COMd frames suggest the names don't mean exactly what they say:
  - `sig_rx_immediate` is greater than `sig_rx_max` in all 57 frames.
  - `sig_background_immediate` is greater than `sig_background_max` in 12 frames.
  - The three RX values take only three distinct sets of values across all 57 frames. They may update only when the satellite receives a packet.

  So "max" is not a simple running maximum of the immediate value. The CLI does not check any relationship between the six values.

- **`RX`:** the guide calls this the "RF side packet counter", with values `<packets_received>, <packets_transmitted>`. The reference decoder names the same two values `rf_packets_received` and `rf_packets_transmitted`. They are plain counts, so no conversion is needed.

  The guide also says "Note that 'RX' = 'AX.25' + 'CSP'", meaning RX should equal the `Ax` and `CSP` counters added together. Its own example beacon satisfies that exactly. The real frames don't:
  - In all 59 real frames (the 57 archive frames and both real fixtures), `rf_packets_received` is exactly 395 more than AX.25 + CSP received.
  - In the same frames, `rf_packets_transmitted` is exactly 13 less than AX.25 + CSP transmitted.
  - The offsets stay constant even as the counters change.

  The CLI does not check this relationship.

- **`Ax`:** the guide calls these "AX.25 packet counters", with values `<packets_received>, <packets_transmitted>`. The reference decoder names them `ax25_packets_received` and `ax25_packets_transmitted`. They are plain counts, so no conversion is needed.

  In all 59 real frames, `ax25_packets_received` equals the digipeater received count that follows the `Digi` label. That suggests every AX.25 packet the satellite received was digipeater traffic, but the guide does not say so. The CLI does not check this.

- **`Digi`, `CSP`, `I2C1`, `I2C2`, `RS485` and `MCU`:** the guide gives each as `<packets_received>, <packets_transmitted>`, except `Digi`, which is `<digipeaterRxCount>, <digipeaterTxCount>`. It describes them as follows:
  - `Digi`: "Digipeater counters"
  - `CSP`: "RF side CSP packet counters"
  - `I2C1`: "I2C1 packet counters"
  - `I2C2`: "I2C2 packet counters"
  - `RS485`: "RS485 packet counters"
  - `MCU`: "CSP interface packet counters"

  The field order and key names match the reference decoder. They are plain counts, so no conversion is needed.

- **The final MCU value:** the guide's example beacon ends `MCU,835,837`, with no trailing comma. Every real frame checked ends differently. All 57 archive frames and both real fixtures end `,MCU,<received>,`, so the transmitted value is missing; the frame ends right after the received value's comma. The CLI handles the end of the frame like this:
  - **Nothing after the comma:** `csp_mcu_transmitted` is `null`. This is every real frame. It is never reported as `0`.
  - **Exactly one unsigned integer** (the guide's form): that number. Zeros stay `0`, so `MCU,0,0` gives `0` and `0`.
  - **Anything else** (for example `837,`, `8x7`, `837,9`, or no comma after the received value): the frame is rejected with an error.

  The reference decoder behaves the same way on all of these cases. It returns `null` when the value is missing, decodes the guide's form, and fails on the malformed endings, though with a raw `ValueError` or end-of-stream exception rather than a named error. This was checked by putting eight hand-made endings through both decoders.

It follows the frame layout from the reference decoder's `comd` type, which cites the Needronix Cormorant ham radio user guide:

- **Bytes 0–15:** a fixed AX.25 UI header, `86a240404040e09e9a728ea4846103f0`. That is CQ-0 ← OM9GRB-0, control `0x03`, PID `0xF0`, with no FCS.
- **Bytes 16 onward:** an ASCII payload, `,COMd,U,<uptime_total>,<uptime_since_last>,R,<reset_count>,V,<mcu_10mv>,Ve,<batt>,T,<temp_cpu>,<temp_pa_ntc>,Sig,<six signal values>,RX,<rf_packets_received>,<rf_packets_transmitted>,Ax,<ax25_packets_received>,<ax25_packets_transmitted>,Digi,<rx>,<tx>,CSP,<rx>,<tx>,I2C1,<rx>,<tx>,I2C2,<rx>,<tx>,RS485,<rx>,<tx>,MCU,<rx>,[<tx>]`. The final `<tx>` is absent in real GRBAlpha frames.

**What the CLI validates:**

- **Exact header:** the first 16 bytes must equal the header above, byte for byte. Any other header is rejected, including a different SSID byte. For example, the other OM9GRB frames from the same pass end the source address with `0x7f` instead of `0x61`, so the CLI rejects them.
- **Payload start:** the byte after the header must be `,`.
- **The whole payload:** forty-three fields (15 labels and 28 values) are checked in order, up to and including `csp_mcu_received`, and each must end with `,`:
  - `COMd`, `U`, `R`, `V`, `Ve`, `T`, `Sig`, `RX`, `Ax`, `Digi`, `CSP`, `I2C1`, `I2C2`, `RS485` and `MCU` must match exactly.
  - Every value must be an unsigned decimal integer (ASCII `0-9` only). That includes `uptime_total`, `uptime_since_last` and `reset_count`.
- **The end of the frame:** after `csp_mcu_received` the payload must either end or be exactly one unsigned integer (`csp_mcu_transmitted`). Nothing else is accepted.
- **Not checked:** there is no FCS/CRC to check, because SatNOGS stores the frame without one.

### Run

```sh
python3 telemetry_decoder.py fixtures/grbalpha_11737297_2025-06-09T18-53-26.bin
# {"uptime_total": 113266941, "uptime_since_last": 1058203, "reset_count": 346, "mcu_10mv": 333, "mcu_volts": 3.33, "batt": 2421, "batt_mv": 8161.9173, "temp_cpu_k": 303, "temp_cpu_c": 29.85, "temp_pa_ntc": 1854, "temp_pa_c": 29.39, "sig_rx_immediate": 1917, "sig_rx_avg": 1751, "sig_rx_max": 1751, "sig_background_immediate": 1003, "sig_background_avg": 998, "sig_background_max": 1022, "rf_packets_received": 63572, "rf_packets_transmitted": 8277857, "ax25_packets_received": 3211, "ax25_packets_transmitted": 3708250, "digipeater_rx_count": 3211, "digipeater_tx_count": 1518149, "csp_received": 59966, "csp_transmitted": 4569620, "i2c1_received": 19774702, "i2c1_transmitted": 107436, "i2c2_received": 106889, "i2c2_transmitted": 41483, "rs485_received": 421130, "rs485_transmitted": 15223593, "csp_mcu_received": 15249184, "csp_mcu_transmitted": null}
```

If a frame is malformed or unreadable, the decoder prints `error: <file>: <reason>` to stderr and exits with code 1.

### Test

```sh
python3 -m unittest discover -s tests -v
```

There are thirty-six tests.

**End-to-end CLI tests:**

- The first real fixture gives `uptime_total` 113266941 s, `uptime_since_last` 1058203 s, `reset_count` 346, `mcu_10mv` 333 (3.33 V), `batt` 2421 (8161.9173 mV), `temp_cpu` 303 K (29.85 °C), `temp_pa_ntc` 1854 (29.39 °C), Sig values `1917,1751,1751,1003,998,1022`, RX counters 63572 and 8277857, and Ax counters 3211 and 3708250.
- The second real fixture gives `uptime_total` 113244337 s, `uptime_since_last` 1035599 s, `reset_count` 346, `mcu_10mv` 334 (3.34 V), `batt` 2447 (8249.5711 mV), `temp_cpu` 290 K (16.85 °C), `temp_pa_ntc` 2411 (17.02 °C), Sig values `1917,1751,1751,1219,1193,1194`, RX counters 63572 and 8276732, and Ax counters 3211 and 3707125.
- The synthetic fixture gives `mcu_10mv` 412 (4.12 V). Its other fields are unchanged from the first real fixture.
- The real frame with its uptime and reset values replaced by `5000,4000` and `0` decodes 5000, 4000 and 0, and those three keys come first in the output.
- `uptime_total` of `1132669.41` and `reset_count` of `-1` are each rejected with a named error.
- A frame truncated to 40 bytes produces an error naming `uptime_since_last`, a nonzero exit code and nothing on stdout.
- The real frame with `batt` changed to `24x1` produces the error `batt is not an unsigned integer: b'24x1'`, a nonzero exit code and nothing on stdout.
- The real frame with `temp_cpu` changed to `3a3` produces the error `temp_cpu is not an unsigned integer: b'3a3'`, a nonzero exit code and nothing on stdout.
- The real frame with the PA NTC reading changed to `0` still decodes. `temp_pa_ntc` is 0 and `temp_pa_c` is `null`.
- The real frame with `temp_pa_ntc` changed to `18z4` produces the error `temp_pa_ntc is not an unsigned integer: b'18z4'`.
- The real frame with `Sig` changed to `Sgi` produces the error `expected signal label b'Sig', got b'Sgi'`.
- The real frame with its Sig values replaced by `1,22,333,4444,5,66` decodes those six values to the six `sig_*` keys in payload order.
- The real frame with a Sig value changed to `9o8` produces the error `sig_background_avg is not an unsigned integer: b'9o8'`.
- The real frame with only five Sig values produces the error `sig_background_max is not an unsigned integer: b'RX'`.
- The real frame with `RX` changed to `XR` produces the error `expected RF packet counter label b'RX', got b'XR'`.
- The real frame with its RX counters replaced by `12,3456` decodes 12 received and 3456 transmitted.
- The real frame with an RX counter changed to `635-2` produces the error `rf_packets_received is not an unsigned integer: b'635-2'`.
- The real frame with only one RX counter produces the error `rf_packets_transmitted is not an unsigned integer: b'Ax'`.
- The real frame with `Ax` changed to `AX` produces the error `expected AX.25 packet counter label b'Ax', got b'AX'`.
- The real frame with its Ax counters replaced by `7,89` decodes 7 received and 89 transmitted, and leaves the RX counters unchanged.
- The real frame with an Ax counter changed to `37O8250` (a letter O) produces the error `ax25_packets_transmitted is not an unsigned integer: b'37O8250'`.
- The real frame with only one Ax counter produces the error `ax25_packets_transmitted is not an unsigned integer: b'Digi'`.
- The real frame with `Digi` changed to `Digl` produces the error `expected digipeater counter label b'Digi', got b'Digl'`.
- `SIG_FIELDS`, the output key list, matches the parser's field layout between `Sig` and `RX`.

**Digi, CSP, I2C1, I2C2, RS485 and MCU tests:**

- Both real fixtures decode all twelve of these values, and `csp_mcu_transmitted` is `null`.
- The real fixture ends `,MCU,15249184,`. The output includes `csp_mcu_transmitted`, it is `None`, and the JSON text says `null`, not `0`.
- Endings of `MCU,835,837`, `MCU,0,0` and `MCU,0,` decode to (835, 837), (0, 0) and (0, `None`).
- Endings of `MCU,835,837,`, `MCU,835,8x7`, `MCU,835,837,9`, `MCU,15249184` (no final comma) and `MCU,` are each rejected with a named error.
- A replacement ending `Digi,1,2,CSP,3,4,I2C1,5,6,I2C2,7,8,RS485,9,10,MCU,11,12` decodes 1 to 12 to the right keys, in payload order, and leaves the Ax counters unchanged.
- Each of the labels `CSP`, `I2C1`, `I2C2`, `RS485` and `MCU` is rejected when misspelled.
- The values `32l1`, `-4569620`, an empty value and `1.5e7` are rejected in the Digi, CSP, I2C2 and RS485 counters.
- A CSP group with only one value is rejected, because the `I2C1` label lands in `csp_transmitted`'s slot.
- `COUNTER_FIELDS`, the output key list, matches the parser's field layout from `RX` to `MCU`.

**`NTC_TABLE` and `ntc_to_celsius` tests:**

- The table has 42 points and starts and ends at the expected values.
- Its ADC values are strictly decreasing.
- Every table point converts exactly.
- Two in-between readings interpolate correctly: 1937 gives 27.51 °C and 78 gives 147.22 °C.
- Readings of 0, 72, 4055 and 4095 return `None`.

### Known caveats

- The reference decoder gives `batt` and `temp_cpu` as raw integers with no units. The units used here come from the Cormorant guide, not the reference decoder. The guide's T field description cross-references Appendix II for the PA NTC value, but the appendix itself does not name the field it applies to.
- `csp_mcu_transmitted` is `null` in every real frame, because the frames end `,MCU,<received>,` with no transmitted value. The guide's example has the value, so the real frames don't match the documented format here. The CLI reports the value as missing and does not guess it.
