use esp_idf_svc::nvs::{EspNvs, EspNvsPartition, NvsDefault};
use esp_idf_sys::EspError;
use log::info;

const NVS_NAMESPACE: &str = "vent_cfg";
const KEY_ROOM: &str = "room";
const KEY_FLOOR: &str = "floor";
const KEY_NAME: &str = "name";
const KEY_INITIALIZED: &str = "init";

/// Device identity manager using NVS for persistent config.
pub struct DeviceIdentity {
    nvs: EspNvs<NvsDefault>,
    eui64: String,
}

impl DeviceIdentity {
    /// Initialize identity manager. Reads EUI-64 from eFuse.
    pub fn new(nvs_partition: EspNvsPartition<NvsDefault>) -> Result<Self, EspError> {
        let nvs = EspNvs::new(nvs_partition, NVS_NAMESPACE, true)?;
        let eui64 = Self::read_eui64();
        info!("Device EUI-64: {}", eui64);

        Ok(Self { nvs, eui64 })
    }

    /// Read the EUI-64 MAC address from ESP32-C6 eFuse.
    fn read_eui64() -> String {
        let mut mac = [0u8; 8];
        unsafe {
            esp_idf_sys::esp_efuse_mac_get_default(mac.as_mut_ptr());
        }
        mac.iter()
            .map(|b| format!("{:02x}", b))
            .collect::<Vec<_>>()
            .join(":")
    }

    /// Get the device's permanent EUI-64 identifier.
    pub fn eui64(&self) -> &str {
        &self.eui64
    }

    /// Check if this is the first boot (no config in NVS).
    pub fn is_first_boot(&self) -> Result<bool, EspError> {
        let mut buf = [0u8; 1];
        match self.nvs.get_raw(KEY_INITIALIZED, &mut buf) {
            Ok(Some(_)) => Ok(false),
            Ok(None) => Ok(true),
            Err(e) => Err(e),
        }
    }

    /// Mark device as initialized in NVS.
    pub fn mark_initialized(&mut self) -> Result<(), EspError> {
        self.nvs.set_raw(KEY_INITIALIZED, &[1])?;
        Ok(())
    }

    /// Get room assignment from NVS.
    pub fn get_room(&self) -> Result<Option<String>, EspError> {
        self.get_string(KEY_ROOM)
    }

    /// Set room assignment in NVS.
    pub fn set_room(&mut self, room: &str) -> Result<(), EspError> {
        self.set_string(KEY_ROOM, room)
    }

    /// Get floor assignment from NVS.
    pub fn get_floor(&self) -> Result<Option<String>, EspError> {
        self.get_string(KEY_FLOOR)
    }

    /// Set floor assignment in NVS.
    pub fn set_floor(&mut self, floor: &str) -> Result<(), EspError> {
        self.set_string(KEY_FLOOR, floor)
    }

    /// Get device name from NVS.
    pub fn get_name(&self) -> Result<Option<String>, EspError> {
        self.get_string(KEY_NAME)
    }

    /// Set device name in NVS.
    pub fn set_name(&mut self, name: &str) -> Result<(), EspError> {
        self.set_string(KEY_NAME, name)
    }

    fn get_string(&self, key: &str) -> Result<Option<String>, EspError> {
        let mut buf = [0u8; 64];
        match self.nvs.get_raw(key, &mut buf) {
            Ok(Some(val)) => {
                let s = core::str::from_utf8(&buf[..val.len()])
                    .unwrap_or_default()
                    .to_string();
                Ok(Some(s))
            }
            Ok(None) => Ok(None),
            Err(e) => Err(e),
        }
    }

    fn set_string(&mut self, key: &str, value: &str) -> Result<(), EspError> {
        self.nvs.set_raw(key, value.as_bytes())?;
        Ok(())
    }

    // -- Write-Ahead Checkpoint for servo position recovery --
    //
    // Inspired by write-ahead logging (WAL), but NOT an append-only log.
    // Three fixed NVS keys are overwritten in place — total storage is
    // constant at 3 bytes regardless of how many commands are processed.
    //
    // NVS keys (each 1 byte, overwritten on every cycle):
    //   "angle"  — checkpoint: last committed (known-good) angle
    //   "target" — intent: target recorded before the move starts
    //   "wal"    — commit flag: 1 = committed, 0 = pending
    //
    // Protocol:
    //   1. write_ahead(target)  — persist intent + clear commit flag  (2 NVS writes)
    //   2. servo moves          — RAM only, no NVS writes
    //   3. commit(angle)        — persist final angle + set flag      (2 NVS writes)
    //
    // Recovery (boot with wal=0):
    //   restore checkpoint, replay pending target
    //
    // Flash wear: 4 NVS writes per command cycle. ESP-IDF NVS is
    // internally log-structured and wear-leveled across pages.
    // With a 24KB NVS partition (~600K effective writes) and 100
    // commands/day, flash wear is not a concern for ~16 years.

    /// Get the last committed (checkpoint) vent angle from NVS.
    pub fn checkpoint_angle(&self) -> Result<Option<u8>, EspError> {
        let mut buf = [0u8; 1];
        match self.nvs.get_raw("angle", &mut buf) {
            Ok(Some(val)) => Ok(Some(val[0])),
            Ok(None) => Ok(None),
            Err(e) => Err(e),
        }
    }

    /// Write-ahead: record target intent and clear the commit flag.
    /// Must be called BEFORE the servo starts moving.
    pub fn write_ahead(&mut self, target: u8) -> Result<(), EspError> {
        self.nvs.set_raw("target", &[target])?;
        self.nvs.set_raw("wal", &[0u8])?;
        Ok(())
    }

    /// Get the pending (write-ahead) target from the last uncommitted move.
    pub fn get_pending(&self) -> Result<Option<u8>, EspError> {
        let mut buf = [0u8; 1];
        match self.nvs.get_raw("target", &mut buf) {
            Ok(Some(val)) => Ok(Some(val[0])),
            Ok(None) => Ok(None),
            Err(e) => Err(e),
        }
    }

    /// Commit: save the final angle as the new checkpoint and set the
    /// commit flag. Called after the servo reaches its target.
    pub fn commit(&mut self, angle: u8) -> Result<(), EspError> {
        self.nvs.set_raw("angle", &[angle])?;
        self.nvs.set_raw("wal", &[1u8])?;
        Ok(())
    }

    /// Check whether the last move was committed.
    /// Returns false if power was lost between write_ahead and commit.
    pub fn is_committed(&self) -> Result<bool, EspError> {
        let mut buf = [0u8; 1];
        match self.nvs.get_raw("wal", &mut buf) {
            Ok(Some(val)) => Ok(val[0] == 1),
            Ok(None) => Ok(true), // no WAL entry = no pending move = committed
            Err(e) => Err(e),
        }
    }
}
