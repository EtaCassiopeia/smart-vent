# DO NOT SEND TO A FAB

These Gerbers + drill file were plotted from `../smart_vent_v1.kicad_pcb`,
which now has a collision-free placement (see issue #46 — all shorts,
clearance violations, and courtyard overlaps are resolved) but **still has
no copper routed**. They exist solely to confirm the fab-export pipeline
itself works and produces the JLCPCB-compatible layer set documented in
[`docs/battery-carrier-board.md` §6](../../../../../docs/battery-carrier-board.md#6-fab-settings-jlcpcb)
— that is the only thing they verify.

Regenerate after routing with:

```
kicad-cli pcb export gerbers --output gerbers-unrouted-with-led/ ../smart_vent_v1.kicad_pcb
kicad-cli pcb export drill   --output gerbers-unrouted-with-led/ ../smart_vent_v1.kicad_pcb
```

(swap in the routed board path once routing is done, and rename the output
directory to drop "unrouted").
