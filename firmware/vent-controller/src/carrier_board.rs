//! Battery carrier board support (see `docs/battery-carrier-board.md`).
//!
//! Cargo-feature gated, no effect on the default always-on-USB build:
//!   * `battery-carrier-board` — power-gated SG90 driver + NiMH pack sense
//!   * `led-indicator`         — status LED (requires `battery-carrier-board`,
//!                               only present on the with-LED PCB variant)
//!
//! Hardware (see the doc's connection map):
//!   GPIO2  -> SG90 signal (existing, LEDC ch0, 50 Hz)
//!   GPIO21 -> servo_en: HIGH = servo powered (2N7002 -> P-FET high-side switch)
//!   GPIO1  -> divider tap, 2M(top)/1M(bottom) from VBAT  (multiply reading by 3)
//!   GPIO22 -> SK6812 data (via 470R), led-indicator only

use esp_idf_hal::delay::FreeRtos;
use esp_idf_hal::gpio::{Output, PinDriver};
use esp_idf_hal::ledc::LedcDriver;

// =====================================================================
// servo (power-gated)
// =====================================================================
//
// Takes an already-constructed `LedcDriver` (build it the same way
// `servo::ServoDriver` does in servo.rs: `LedcTimerDriver` at 50 Hz +
// `LedcDriver::new(channel, &timer, gpio2)`) rather than raw timer/channel
// peripherals -- tying an independent timer-generic and channel-generic
// together to the same SpeedMode without that pre-built driver requires
// extra trait bounds this module doesn't need to carry.
pub mod servo {
    use super::*;
    use esp_idf_hal::gpio::Pin;

    const PERIOD_MS: f32 = 20.0; // 50 Hz
    const MIN_PULSE_MS: f32 = 1.0; // 90 deg
    const MAX_PULSE_MS: f32 = 2.0; // 180 deg
    const MIN_ANGLE: f32 = 90.0;
    const MAX_ANGLE: f32 = 180.0;

    /// Let the rail settle + servo energise before commanding a position.
    const POWER_SETTLE_MS: u32 = 50;
    /// Worst case 90->180 on an SG90 is ~300 ms; pad it.
    const TRAVEL_MS: u32 = 500;
    /// Optional dwell at target before cutting power.
    const HOLD_MS: u32 = 100;

    pub struct Servo<'d, EN: Pin> {
        pwm: LedcDriver<'d>,
        enable: PinDriver<'d, EN, Output>,
        max_duty: u32,
    }

    impl<'d, EN: Pin> Servo<'d, EN> {
        /// `pwm` is a pre-built 50 Hz, 14-bit `LedcDriver` on GPIO2 (see
        /// module note above for how to build one). `enable` is an output
        /// PinDriver on GPIO21 (already `PinDriver::output`, default state
        /// low => servo off).
        pub fn new(pwm: LedcDriver<'d>, enable: PinDriver<'d, EN, Output>) -> anyhow::Result<Self> {
            let max_duty = pwm.get_max_duty();
            Ok(Self {
                pwm,
                enable,
                max_duty,
            })
        }

        fn angle_to_duty(&self, angle: f32) -> u32 {
            let a = angle.clamp(MIN_ANGLE, MAX_ANGLE);
            let frac = (a - MIN_ANGLE) / (MAX_ANGLE - MIN_ANGLE);
            let pulse_ms = MIN_PULSE_MS + frac * (MAX_PULSE_MS - MIN_PULSE_MS);
            ((pulse_ms / PERIOD_MS) * self.max_duty as f32) as u32
        }

        /// Power up -> command position -> wait for travel -> cut power.
        /// The louver holds position by friction once unpowered.
        ///
        /// If your louver back-drives the gear, drop the final
        /// `power_off()` call (servo keeps holding torque at the cost of
        /// ~10 mA continuous).
        pub fn move_to(&mut self, angle: f32) -> anyhow::Result<()> {
            self.power_on()?;
            FreeRtos::delay_ms(POWER_SETTLE_MS);

            self.pwm.set_duty(self.angle_to_duty(angle))?;
            self.pwm.enable()?;

            FreeRtos::delay_ms(TRAVEL_MS + HOLD_MS);

            self.pwm.set_duty(0)?;
            self.pwm.disable()?;
            self.power_off()?;
            Ok(())
        }

        fn power_on(&mut self) -> anyhow::Result<()> {
            self.enable.set_high()?;
            Ok(())
        }
        fn power_off(&mut self) -> anyhow::Result<()> {
            self.enable.set_low()?;
            Ok(())
        }
    }
}

// =====================================================================
// battery
// =====================================================================
pub mod battery {
    use esp_idf_hal::adc::attenuation::DB_11;
    use esp_idf_hal::adc::oneshot::config::{AdcChannelConfig, Calibration};
    use esp_idf_hal::adc::oneshot::{AdcChannelDriver, AdcDriver};
    use esp_idf_hal::adc::Adc;
    use esp_idf_hal::gpio::ADCPin;
    use esp_idf_hal::peripheral::Peripheral;

    /// Divider ratio (2M top / 1M bottom => tap = Vpack / 3).
    const DIVIDER: f32 = 3.0;
    const SAMPLES: usize = 16;

    /// 4-cell NiMH thresholds (pack mV). NiMH discharge is very flat, so
    /// treat this as a coarse "where am I" gauge, not a true fuel gauge.
    ///   ~5600 fresh off charger (1.4 V/cell)
    ///   ~4800 nominal           (1.2 V/cell, most of the run)
    ///   ~4300 getting low
    ///   ~4000 stop here         (1.0 V/cell — below this you risk cell reversal)
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum State {
        Good,     // > 4800
        Ok,       // 4400..=4800
        Low,      // 4100..=4399
        Critical, // < 4100
    }

    impl State {
        pub fn from_mv(pack_mv: u32) -> Self {
            match pack_mv {
                m if m > 4800 => State::Good,
                m if m >= 4400 => State::Ok,
                m if m >= 4100 => State::Low,
                _ => State::Critical,
            }
        }
    }

    pub struct PackSense<'d, A: Adc, P: ADCPin<Adc = A>> {
        chan: AdcChannelDriver<'d, P, AdcDriver<'d, A>>,
    }

    impl<'d, A: Adc, P: ADCPin<Adc = A>> PackSense<'d, A, P> {
        /// `adc` = peripherals.adc1, `pin` = GPIO1 (A1).
        pub fn new(
            adc: impl Peripheral<P = A> + 'd,
            pin: impl Peripheral<P = P> + 'd,
        ) -> anyhow::Result<Self> {
            let adc = AdcDriver::new(adc)?;
            let cfg = AdcChannelConfig {
                attenuation: DB_11,
                calibration: Calibration::Curve,
                ..Default::default()
            };
            let chan = AdcChannelDriver::new(adc, pin, &cfg)?;
            Ok(Self { chan })
        }

        /// Averaged pack voltage in millivolts (divider already compensated).
        pub fn read_mv(&mut self) -> anyhow::Result<u32> {
            let mut acc: u32 = 0;
            for _ in 0..SAMPLES {
                acc += self.chan.read()? as u32; // calibrated mV at the tap
            }
            let tap_mv = acc / SAMPLES as u32;
            Ok((tap_mv as f32 * DIVIDER) as u32)
        }

        pub fn read_state(&mut self) -> anyhow::Result<State> {
            Ok(State::from_mv(self.read_mv()?))
        }
    }
}

// =====================================================================
// indicator (SK6812 single LED) — `led-indicator` feature only
// =====================================================================
#[cfg(feature = "led-indicator")]
pub mod indicator {
    use super::battery::State;
    use esp_idf_hal::delay::FreeRtos;
    use smart_leds::{SmartLedsWrite, RGB8};
    use std::iter::once;
    use ws2812_esp32_rmt_driver::Ws2812Esp32Rmt;

    const OFF: RGB8 = RGB8 { r: 0, g: 0, b: 0 };
    const GREEN: RGB8 = RGB8 { r: 0, g: 24, b: 0 };
    const AMBER: RGB8 = RGB8 { r: 28, g: 14, b: 0 };
    const RED: RGB8 = RGB8 { r: 30, g: 0, b: 0 };
    const BLUE: RGB8 = RGB8 { r: 0, g: 0, b: 40 }; // identify
    const WHITE: RGB8 = RGB8 {
        r: 16,
        g: 16,
        b: 16,
    }; // installing / pairing

    /// What the LED is being asked to communicate, in priority order.
    /// Identify always wins -- it's the one a person is actively looking
    /// at the hardware for.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum Event {
        Identify,
        Install(InstallState),
        CommandResult { ok: bool },
        Battery(State),
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum InstallState {
        AwaitingCommission,
        Pairing,
        Commissioned,
        Error,
    }

    pub struct Indicator<'d> {
        ws: Ws2812Esp32Rmt<'d>,
    }

    impl<'d> Indicator<'d> {
        pub fn new(
            channel: impl esp_idf_hal::peripheral::Peripheral<P = impl esp_idf_hal::rmt::RmtChannel>
                + 'd,
            pin: impl esp_idf_hal::peripheral::Peripheral<P = impl esp_idf_hal::gpio::OutputPin> + 'd,
        ) -> anyhow::Result<Self> {
            let ws = Ws2812Esp32Rmt::new(channel, pin)
                .map_err(|e| anyhow::anyhow!("ws2812 init failed: {e}"))?;
            Ok(Self { ws })
        }

        fn set(&mut self, c: RGB8) -> anyhow::Result<()> {
            self.ws
                .write(once(c))
                .map_err(|e| anyhow::anyhow!("ws2812 write failed: {e}"))?;
            Ok(())
        }

        pub fn off(&mut self) -> anyhow::Result<()> {
            self.set(OFF)
        }

        pub fn show(&mut self, event: Event) -> anyhow::Result<()> {
            match event {
                Event::Identify => self.identify(4),
                Event::Install(state) => self.install(state),
                Event::CommandResult { ok } => self.command_result(ok),
                Event::Battery(state) => self.show_battery(state, 600),
            }
        }

        /// "Find this vent" -- the primary use case.
        pub fn identify(&mut self, blinks: u8) -> anyhow::Result<()> {
            for _ in 0..blinks {
                self.set(BLUE)?;
                FreeRtos::delay_ms(200);
                self.off()?;
                FreeRtos::delay_ms(200);
            }
            Ok(())
        }

        fn install(&mut self, state: InstallState) -> anyhow::Result<()> {
            match state {
                InstallState::AwaitingCommission => {
                    for _ in 0..3 {
                        self.set(WHITE)?;
                        FreeRtos::delay_ms(400);
                        self.off()?;
                        FreeRtos::delay_ms(400);
                    }
                }
                InstallState::Pairing => {
                    for _ in 0..6 {
                        self.set(BLUE)?;
                        FreeRtos::delay_ms(150);
                        self.off()?;
                        FreeRtos::delay_ms(150);
                    }
                }
                InstallState::Commissioned => {
                    self.set(GREEN)?;
                    FreeRtos::delay_ms(1000);
                    self.off()?;
                }
                InstallState::Error => {
                    for _ in 0..5 {
                        self.set(RED)?;
                        FreeRtos::delay_ms(150);
                        self.off()?;
                        FreeRtos::delay_ms(150);
                    }
                }
            }
            Ok(())
        }

        fn command_result(&mut self, ok: bool) -> anyhow::Result<()> {
            self.set(if ok { GREEN } else { RED })?;
            FreeRtos::delay_ms(150);
            self.off()
        }

        pub fn show_battery(&mut self, state: State, ms: u32) -> anyhow::Result<()> {
            let c = match state {
                State::Good | State::Ok => GREEN,
                State::Low => AMBER,
                State::Critical => RED,
            };
            self.set(c)?;
            FreeRtos::delay_ms(ms);
            self.off()
        }
    }
}
