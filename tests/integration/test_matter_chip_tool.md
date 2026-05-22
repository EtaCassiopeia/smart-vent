# Matter chip-tool Integration Test Procedure

Manual test procedure for validating Matter Window Covering functionality using chip-tool.

## Prerequisites

- ESP32-C6 flashed with Matter-enabled firmware
- chip-tool installed (from connectedhomeip SDK)
- OTBR running with Thread network active

## 1. Commission Device

```bash
# Get Thread dataset from OTBR
docker exec otbr ot-ctl dataset active -x

# Commission via BLE-Thread (use pairing code from serial output)
chip-tool pairing ble-thread 1 hex:<dataset> <passcode> <discriminator>
```

- [ ] Commission succeeds without errors
- [ ] Serial output shows "Matter: commissioned into fabric"
- [ ] Device appears as child in `docker exec otbr ot-ctl child table`

## 2. Basic Operations

### Open (UpOrOpen)
```bash
chip-tool windowcovering up-or-open 1 1
```
- [ ] Servo moves to 180° (fully open)
- [ ] Serial shows "Matter: target position set to 0/10000"
- [ ] `CurrentPositionLiftPercent100ths` reads 0

### Close (DownOrClose)
```bash
chip-tool windowcovering down-or-close 1 1
```
- [ ] Servo moves to 90° (fully closed)
- [ ] Serial shows "Matter: target position set to 10000/10000"
- [ ] `CurrentPositionLiftPercent100ths` reads 10000

### Set Percentage (GoToLiftPercentage)
```bash
chip-tool windowcovering go-to-lift-percentage 5000 1 1
```
- [ ] Servo moves to ~135° (50% open)
- [ ] Serial shows "Matter: target position set to 5000/10000"

### Read Position
```bash
chip-tool windowcovering read current-position-lift-percent100ths 1 1
```
- [ ] Returns correct percent100ths value

### Read Operational Status
```bash
chip-tool windowcovering read operational-status 1 1
```
- [ ] Returns 0 when stopped
- [ ] Returns non-zero during movement (test by reading while servo is moving)

## 3. Edge Cases

### Boundary Values
```bash
chip-tool windowcovering go-to-lift-percentage 0 1 1      # Fully open
chip-tool windowcovering go-to-lift-percentage 10000 1 1   # Fully closed
chip-tool windowcovering go-to-lift-percentage 1 1 1       # Near-open
chip-tool windowcovering go-to-lift-percentage 9999 1 1    # Near-closed
```
- [ ] All values map correctly (no servo overshoot)

### Stop Motion
```bash
chip-tool windowcovering go-to-lift-percentage 0 1 1   # Start long move
# Immediately:
chip-tool windowcovering stop-motion 1 1
```
- [ ] Servo stops at intermediate position
- [ ] Position report reflects actual stop point

## 4. CoAP Coexistence

### CoAP command during Matter control
```bash
# Set position via Matter
chip-tool windowcovering go-to-lift-percentage 5000 1 1

# Read position via CoAP
aiocoap-client coap://[<device-ipv6>]/vent/position
```
- [ ] CoAP returns angle=135, state=partial

### CoAP command, then Matter read
```bash
# Set target via CoAP
aiocoap-client -m PUT coap://[<device-ipv6>]/vent/target --payload <cbor-135>

# Read via Matter
chip-tool windowcovering read current-position-lift-percent100ths 1 1
```
- [ ] Matter reports 5000 (50%) after servo reaches target

## 5. Persistence

### Reboot test
```bash
chip-tool windowcovering go-to-lift-percentage 3000 1 1
# Wait for servo to reach target, then power-cycle device
chip-tool windowcovering read current-position-lift-percent100ths 1 1
```
- [ ] After reboot, position reads ~3000

### Factory reset
- [ ] After `matter_bridge_factory_reset()`, device re-enters BLE advertising
- [ ] Can be re-commissioned

## 6. Binary Size Check

```bash
ls -la firmware/vent-controller/target/riscv32imac-esp-espidf/release/vent-controller
```
- [ ] Binary fits within 1.9MB partition (< 1,966,080 bytes)
