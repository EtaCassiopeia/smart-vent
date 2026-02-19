use esp_idf_sys::EspError;
use log::info;

/// Thread network configuration.
pub struct ThreadConfig {
    pub network_name: String,
    pub channel: u8,
    pub panid: u16,
}

impl Default for ThreadConfig {
    fn default() -> Self {
        Self {
            network_name: "VentNet".into(),
            channel: 15,
            panid: 0x1234,
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

            esp_idf_sys::otDatasetCreateNewNetwork(instance, &mut dataset);

            dataset.mChannel = self.config.channel as u16;
            dataset.mPanId = self.config.panid;

            let name_bytes = self.config.network_name.as_bytes();
            let len = name_bytes.len().min(16);
            dataset.mNetworkName.m8[..len].copy_from_slice(
                &name_bytes[..len].iter().map(|&b| b as i8).collect::<Vec<_>>(),
            );

            esp_idf_sys::otDatasetSetActive(instance, &dataset);

            esp_idf_sys::otIp6SetEnabled(instance, true);
            esp_idf_sys::otThreadSetEnabled(instance, true);

            info!(
                "OpenThread started on channel {}, PAN ID 0x{:04x}",
                self.config.channel, self.config.panid
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

    /// Get the RSSI of the last received packet.
    pub fn get_rssi(&self) -> i8 {
        unsafe {
            let instance = esp_idf_sys::esp_openthread_get_instance();
            let mut parent_info: esp_idf_sys::otRouterInfo = std::mem::zeroed();
            if esp_idf_sys::otThreadGetParentInfo(instance, &mut parent_info)
                == esp_idf_sys::OT_ERROR_NONE as u32
            {
                parent_info.mRloc16 as i8
            } else {
                -128
            }
        }
    }
}
