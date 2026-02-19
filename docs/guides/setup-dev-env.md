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
cargo build
```

The first build will download and compile ESP-IDF (takes several minutes).

### 5. Run Host Tests

```bash
# State machine and protocol tests run on your host machine
cd firmware/shared-protocol
cargo test

cd ../vent-controller
cargo test --lib
```

## Python Environment (Hub + Simulator)

### 1. Install Python 3.11+

```bash
# macOS
brew install python@3.11

# Ubuntu/Debian
sudo apt install python3.11 python3.11-venv
```

### 2. Create Virtual Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install Hub

```bash
cd hub
pip install -e ".[dev]"
```

### 4. Install Simulator

```bash
cd tools/simulator
pip install -e .
```

### 5. Run Tests

```bash
# Hub unit tests
cd hub
pytest

# Integration tests (requires simulator)
cd ..
pytest tests/integration/
```

## IDE Setup

### VS Code

Recommended extensions:
- `rust-analyzer` — Rust language support
- `ms-python.python` — Python support
- `ms-python.pylint` — Linting

Settings for the firmware workspace:

```json
{
    "rust-analyzer.cargo.target": "riscv32imac-esp-espidf",
    "rust-analyzer.checkOnSave.allTargets": false
}
```
