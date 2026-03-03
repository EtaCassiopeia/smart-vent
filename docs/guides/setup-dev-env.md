# Development Environment Setup

## Rust Toolchain (Firmware)

### 1. Install espup

```bash
cargo install espup
espup install
```

This installs the Rust ESP toolchain (fork with Xtensa + RISC-V support).

### 2. Install Build Tools

```bash
cargo install ldproxy espflash cargo-espflash
```

### 3. Source Environment

Add to your shell profile:

```bash
. $HOME/export-esp.sh
```

### 4. Verify

```bash
cd firmware/vent-controller
cargo build --release
```

The first build downloads **ESP-IDF v5.2.3** and compiles the CHIP SDK via the
`esp_matter` component (~1.3.x). This takes several minutes. Subsequent builds
are incremental.

**Note:** The firmware uses the [ESP-IDF Component Manager](https://components.espressif.com/) to pull `esp_matter` and its transitive dependencies automatically during the first build. No manual submodule setup is required.

> **Version compatibility:** The firmware requires ESP-IDF v5.2.3 with
> `esp_matter ~1.3.x`. Other ESP-IDF versions (v5.3, v5.4) have known
> incompatibilities with the CHIP SDK (C++ template parsing errors, missing
> `operator==` implementations). The version is pinned in
> `firmware/vent-controller/.cargo/config.toml`.

### 5. Run Host Tests

```bash
# State machine and protocol tests run on your host machine
cd firmware/shared-protocol
cargo test
```

## Python Environment (Hub + Simulator)

Run all commands from the **project root** directory.

### 1. Install Python 3.11–3.13

Python 3.14+ may have compatibility issues with some dependencies. Any version from 3.11 to 3.13 works.

```bash
# macOS
brew install python@3.13

# Ubuntu/Debian
sudo apt install python3.13 python3.13-venv
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Once activated, `python` and `pip` point to the venv — no version suffix needed.

### 3. Install Hub and Simulator

```bash
pip install -e "hub/.[dev]"
pip install -e tools/simulator
```

### 4. Run Tests

```bash
# Hub unit tests
pytest hub/tests/

# Integration tests (requires simulator)
pytest tests/integration/
```

## IDE Setup

Both editors need rust-analyzer configured to target the ESP32-C6 chip, otherwise you'll see false errors on ESP-IDF code.

### Zed

Settings are already included in the repo at `.zed/settings.json`. No setup needed.

### VS Code

Recommended extensions:
- `rust-analyzer` — Rust language support
- `ms-python.python` — Python support
- `ms-python.pylint` — Linting

Add to `.vscode/settings.json`:

```json
{
    "rust-analyzer.cargo.target": "riscv32imac-esp-espidf",
    "rust-analyzer.checkOnSave.allTargets": false
}
```
