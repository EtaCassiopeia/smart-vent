use esp_idf_hal::ledc::LedcDriver;
use esp_idf_sys::EspError;

/// SG90 servo PWM parameters.
const PWM_FREQ_HZ: u32 = 50;
const MIN_PULSE_US: u32 = 500;   // 0° position
const MAX_PULSE_US: u32 = 2500;  // 180° position
const PERIOD_US: u32 = 20_000;   // 50 Hz = 20ms

/// Step delay in milliseconds for gradual movement.
pub const STEP_DELAY_MS: u32 = 15;

/// Servo driver wrapping LEDC PWM.
pub struct ServoDriver<'d> {
    ledc: LedcDriver<'d>,
    max_duty: u32,
}

impl<'d> ServoDriver<'d> {
    /// Create a new servo driver on the given LEDC channel and GPIO pin.
    pub fn new(
        ledc: LedcDriver<'d>,
    ) -> Result<Self, EspError> {
        let max_duty = ledc.get_max_duty();
        Ok(Self { ledc, max_duty })
    }

    /// Set servo angle (0–180 degrees).
    pub fn set_angle(&mut self, angle: u8) -> Result<(), EspError> {
        let duty = self.angle_to_duty(angle);
        self.ledc.set_duty(duty)?;
        Ok(())
    }

    /// Convert angle (0–180) to LEDC duty cycle value.
    fn angle_to_duty(&self, angle: u8) -> u32 {
        let angle = angle.min(180) as u32;
        let pulse_us = MIN_PULSE_US + (angle * (MAX_PULSE_US - MIN_PULSE_US)) / 180;
        (pulse_us * self.max_duty) / PERIOD_US
    }

    /// Disable PWM output (stop holding servo position).
    pub fn disable(&mut self) -> Result<(), EspError> {
        self.ledc.set_duty(0)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    // Servo hardware tests require ESP32 target.
    // Use the state machine tests in state.rs for host-side testing.
    // Integration tests run on-device via `cargo run`.
}
