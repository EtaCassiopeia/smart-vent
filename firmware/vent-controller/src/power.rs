use esp_idf_sys::EspError;
use log::info;
use std::time::Duration;

/// Power mode configuration.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PowerMode {
    /// Always on, MTD role. For USB-powered devices.
    AlwaysOn,
    /// Sleepy End Device with configurable poll period. For battery-powered devices.
    Sed { poll_period_ms: u32 },
}

impl PowerMode {
    pub fn from_nvs_str(s: &str, poll_ms: u32) -> Self {
        match s {
            "sed" => PowerMode::Sed {
                poll_period_ms: poll_ms,
            },
            _ => PowerMode::AlwaysOn,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            PowerMode::AlwaysOn => "always_on",
            PowerMode::Sed { .. } => "sed",
        }
    }

    pub fn poll_period_ms(&self) -> u32 {
        match self {
            PowerMode::AlwaysOn => 0,
            PowerMode::Sed { poll_period_ms } => *poll_period_ms,
        }
    }
}

/// Power manager handling deep sleep and SED configuration.
pub struct PowerManager {
    mode: PowerMode,
}

impl PowerManager {
    pub fn new(mode: PowerMode) -> Self {
        Self { mode }
    }

    pub fn mode(&self) -> PowerMode {
        self.mode
    }

    /// Configure Thread SED poll period if in SED mode.
    pub fn configure_sed(&self) -> Result<(), EspError> {
        if let PowerMode::Sed { poll_period_ms } = self.mode {
            info!("Configuring SED mode with poll period {}ms", poll_period_ms);
            unsafe {
                let instance = esp_idf_sys::esp_openthread_get_instance();
                // Set the poll period for the sleepy end device
                esp_idf_sys::otLinkSetPollPeriod(instance, poll_period_ms);
            }
        } else {
            info!("Power mode: always-on (MTD)");
        }
        Ok(())
    }

    /// Enter deep sleep for the specified duration.
    /// State should be saved to NVS before calling this.
    #[allow(unreachable_code)]
    pub fn enter_deep_sleep(&self, duration: Duration) -> ! {
        let us = duration.as_micros() as u64;
        info!("Entering deep sleep for {}ms", duration.as_millis());

        unsafe {
            esp_idf_sys::esp_sleep_enable_timer_wakeup(us);
            esp_idf_sys::esp_deep_sleep_start();
        }

        unreachable!()
    }

    /// Check if the device woke from deep sleep.
    pub fn woke_from_sleep() -> bool {
        unsafe {
            let cause = esp_idf_sys::esp_sleep_get_wakeup_cause();
            cause != esp_idf_sys::esp_sleep_source_t_ESP_SLEEP_WAKEUP_UNDEFINED
        }
    }

    /// Get the wakeup cause as a string.
    pub fn wakeup_cause_str() -> &'static str {
        unsafe {
            match esp_idf_sys::esp_sleep_get_wakeup_cause() {
                esp_idf_sys::esp_sleep_source_t_ESP_SLEEP_WAKEUP_TIMER => "timer",
                esp_idf_sys::esp_sleep_source_t_ESP_SLEEP_WAKEUP_GPIO => "gpio",
                esp_idf_sys::esp_sleep_source_t_ESP_SLEEP_WAKEUP_UNDEFINED => "fresh_boot",
                _ => "other",
            }
        }
    }
}
