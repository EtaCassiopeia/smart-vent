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

    /// Get the last finalized vent angle from NVS.
    pub fn get_saved_angle(&self) -> Result<Option<u8>, EspError> {
        let mut buf = [0u8; 1];
        match self.nvs.get_raw("angle", &mut buf) {
            Ok(Some(val)) => Ok(Some(val[0])),
            Ok(None) => Ok(None),
            Err(e) => Err(e),
        }
    }

    /// Save finalized vent angle to NVS.
    pub fn save_angle(&mut self, angle: u8) -> Result<(), EspError> {
        self.nvs.set_raw("angle", &[angle])?;
        Ok(())
    }

    /// Record a pending move command (write-ahead). Called before
    /// the servo starts moving so the target survives a power loss.
    pub fn save_pending_target(&mut self, target: u8) -> Result<(), EspError> {
        self.nvs.set_raw("target", &[target])?;
        self.nvs.set_raw("fin", &[0u8])?; // clear finalized flag
        Ok(())
    }

    /// Get the pending target angle written before the last move started.
    pub fn get_pending_target(&self) -> Result<Option<u8>, EspError> {
        let mut buf = [0u8; 1];
        match self.nvs.get_raw("target", &mut buf) {
            Ok(Some(val)) => Ok(Some(val[0])),
            Ok(None) => Ok(None),
            Err(e) => Err(e),
        }
    }

    /// Mark the current move as complete. Saves final angle and sets
    /// the finalized flag atomically (as far as NVS allows).
    pub fn finalize_move(&mut self, angle: u8) -> Result<(), EspError> {
        self.save_angle(angle)?;
        self.nvs.set_raw("fin", &[1u8])?;
        Ok(())
    }

    /// Check whether the last move command completed successfully.
    /// Returns false if power was lost mid-move.
    pub fn is_finalized(&self) -> Result<bool, EspError> {
        let mut buf = [0u8; 1];
        match self.nvs.get_raw("fin", &mut buf) {
            Ok(Some(val)) => Ok(val[0] == 1),
            Ok(None) => Ok(true), // no flag = no pending command = finalized
            Err(e) => Err(e),
        }
    }
}
