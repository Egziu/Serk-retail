# Hardware compatibility

**Physically qualified devices: none.** No hardware was available to this session.

| Model | Firmware | OS | Connection | Adapter | Features | Real test date | Status |
|---|---|---|---|---|---|---|---|
| *(none)* | | | | | | | |

## Simulator coverage (not hardware qualification)

`serk_retail/devices/printer.py` — `SimulatedEscPosPrinter`

| Behaviour | Simulated | Test |
|---|---|---|
| ESC/POS init `ESC @`, partial cut `GS V A n`, drawer kick `ESC p 0 25 250` bytes | ✓ | test_08 counts `ESC p` occurrences |
| Acknowledged print | ✓ | test_01 |
| Paper out → Failed (drawer kick already sent) | ✓ | test_08 |
| Offline → Failed | ✓ (not separately asserted) | — |
| Timeout → Delivery Unknown; resend refused | ✓ | test_08 |
| 80 mm (48 col) layout | ✓ | test_01 |
| 58 mm (32 col) layout | rendered, not asserted | — |
| Amharic/Tigrinya | ✗ ASCII only (R-11) | — |

Next: qualify one locally available 80 mm ESC/POS USB/network printer and one cash drawer on the
target OS; record results here with dates and evidence photos/logs.
