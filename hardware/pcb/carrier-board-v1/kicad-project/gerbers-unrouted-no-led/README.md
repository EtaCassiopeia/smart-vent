# DO NOT SEND TO A FAB

These Gerbers + drill file were plotted from `../smart_vent_v1_no_led.kicad_pcb`,
which has **no copper routed** — only placeholder footprint placement (with
known overlaps/shorts, see `../README.md`). They exist solely to confirm
the fab-export pipeline itself works and produces the JLCPCB-compatible
layer set documented in
[`docs/battery-carrier-board.md` §6](../../../../../docs/battery-carrier-board.md#6-fab-settings-jlcpcb)
— that is the only thing they verify.

Regenerate after routing with:

```
kicad-cli pcb export gerbers --output gerbers-unrouted-no-led/ ../smart_vent_v1_no_led.kicad_pcb
kicad-cli pcb export drill   --output gerbers-unrouted-no-led/ ../smart_vent_v1_no_led.kicad_pcb
```

(swap in the routed board path once #46 is done, and rename the output
directory to drop "unrouted").
