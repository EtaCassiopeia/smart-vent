use esp_idf_sys::EspError;
use log::info;

/// Thread network configuration.
///
/// All devices on the same Thread network must share the same network key,
/// channel, PAN ID, and network name. These must match the OTBR's active
/// dataset.
///
/// Default values are for development only. For production, generate unique
/// credentials via `docker exec otbr ot-ctl dataset init new` and update
/// both the OTBR and this config to match.
pub struct ThreadConfig {
    pub network_name: String,
    pub channel: u8,
    pub panid: u16,
    pub network_key: [u8; 16],
}

impl Default for ThreadConfig {
    fn default() -> Self {
        Self {
            network_name: "VentNet".into(),
            channel: 25,
            panid: 0xabcd,
            // Development-only network key. Replace for production.
            network_key: [
                0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
                0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
            ],
        }
    }
}

/// Thread network manager.
///
/// Handles OpenThread initialization, network joining, and IPv6 address management
/// using the ESP-IDF OpenThread bindings.
pub struct ThreadManager {
    config: ThreadConfig,
    connected: bool,
}

impl ThreadManager {
    pub fn new(config: ThreadConfig) -> Self {
        Self {
            config,
            connected: false,
        }
    }

    /// Initialize the IEEE 802.15.4 radio and OpenThread stack.
    pub fn init(&mut self) -> Result<(), EspError> {
        info!("Initializing OpenThread stack...");

        unsafe {
            let cfg = esp_idf_sys::esp_openthread_platform_config_t {
                radio_config: esp_idf_sys::esp_openthread_radio_config_t {
                    radio_mode: esp_idf_sys::esp_openthread_radio_mode_t_RADIO_MODE_NATIVE,
                    ..Default::default()
                },
                host_config: esp_idf_sys::esp_openthread_host_connection_config_t {
                    host_connection_mode:
                        esp_idf_sys::esp_openthread_host_connection_mode_t_HOST_CONNECTION_MODE_NONE,
                    ..Default::default()
                },
                port_config: Default::default(),
            };

            esp_idf_sys::esp!(esp_idf_sys::esp_openthread_init(&cfg))?;

            let instance = esp_idf_sys::esp_openthread_get_instance();
            let mut dataset: esp_idf_sys::otOperationalDataset = std::mem::zeroed();

            // Channel
            dataset.mChannel = self.config.channel as u16;
            dataset.mComponents.mIsChannelPresent = true;

            // PAN ID
            dataset.mPanId = self.config.panid;
            dataset.mComponents.mIsPanIdPresent = true;

            // Network name
            dataset.mComponents.mIsNetworkNamePresent = true;
            let name_bytes = self.config.network_name.as_bytes();
            let len = name_bytes.len().min(16);
            dataset.mNetworkName.m8[..len].copy_from_slice(
                &name_bytes[..len],
            );

            // Network key — required to join an existing network
            dataset.mNetworkKey.m8 = self.config.network_key;
            dataset.mComponents.mIsNetworkKeyPresent = true;

            esp_idf_sys::otDatasetSetActive(instance, &dataset);

            esp_idf_sys::otIp6SetEnabled(instance, true);
            esp_idf_sys::otThreadSetEnabled(instance, true);

            info!(
                "OpenThread started on channel {}, PAN ID 0x{:04x}, network '{}'",
                self.config.channel, self.config.panid, self.config.network_name
            );
        }

        Ok(())
    }

    /// Run the OpenThread processing loop. Call this periodically.
    pub fn process(&mut self) -> Result<(), EspError> {
        unsafe {
            esp_idf_sys::esp_openthread_launch_mainloop();
        }
        Ok(())
    }

    /// Get the device's mesh-local IPv6 address as a string.
    pub fn get_ipv6_address(&self) -> Option<String> {
        unsafe {
            let instance = esp_idf_sys::esp_openthread_get_instance();
            let ml_eid = esp_idf_sys::otThreadGetMeshLocalEid(instance);
            if ml_eid.is_null() {
                return None;
            }

            let addr = &*ml_eid;
            Some(format!(
                "{:02x}{:02x}:{:02x}{:02x}:{:02x}{:02x}:{:02x}{:02x}:{:02x}{:02x}:{:02x}{:02x}:{:02x}{:02x}:{:02x}{:02x}",
                addr.mFields.m8[0], addr.mFields.m8[1],
                addr.mFields.m8[2], addr.mFields.m8[3],
                addr.mFields.m8[4], addr.mFields.m8[5],
                addr.mFields.m8[6], addr.mFields.m8[7],
                addr.mFields.m8[8], addr.mFields.m8[9],
                addr.mFields.m8[10], addr.mFields.m8[11],
                addr.mFields.m8[12], addr.mFields.m8[13],
                addr.mFields.m8[14], addr.mFields.m8[15],
            ))
        }
    }

    /// Check if the device is connected to a Thread network.
    pub fn is_connected(&self) -> bool {
        unsafe {
            let instance = esp_idf_sys::esp_openthread_get_instance();
            let role = esp_idf_sys::otThreadGetDeviceRole(instance);
            role >= 2 // child=2, router=3, leader=4
        }
    }

    /// Get the current Thread device role as a string.
    pub fn role_str(&self) -> &'static str {
        unsafe {
            let instance = esp_idf_sys::esp_openthread_get_instance();
            let role = esp_idf_sys::otThreadGetDeviceRole(instance);
            match role {
                0 => "disabled",
                1 => "detached",
                2 => "child",
                3 => "router",
                4 => "leader",
                _ => "unknown",
            }
        }
    }

    /// Get the average RSSI of the link to the parent router.
    pub fn get_rssi(&self) -> i8 {
        unsafe {
            let instance = esp_idf_sys::esp_openthread_get_instance();
            let mut avg_rssi: i8 = -128;
            let err = esp_idf_sys::otThreadGetParentAverageRssi(instance, &mut avg_rssi);
            if err == esp_idf_sys::otError_OT_ERROR_NONE as u32 {
                avg_rssi
            } else {
                -128
            }
        }
    }
}
