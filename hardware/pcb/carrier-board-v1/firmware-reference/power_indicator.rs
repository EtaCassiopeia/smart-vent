//! Power + indicator support for the smart-vent ESP32-C6 (XIAO) build.
//!
//! Adds three things to `vent-controller`:
//!   * `servo`     — power-gated SG90 driver (cuts VCC between moves to save battery)
//!   * `battery`   — 4-cell NiMH pack voltage sense via a 1:3 divider on A1/GPIO1
//!   * `indicator` — SK6812 status LED: battery colour + "identify / find this vent" blink
//!
//! Hardware assumptions (see wiring map):
//!   GPIO2  -> SG90 signal (LEDC ch0, 50 Hz)
//!   GPIO21 -> servo_en: HIGH = servo powered (drives 2N7002 -> P-FET high-side switch)
//!   GPIO1  -> divider tap, 2M(top)/1M(bottom) from VBAT  (multiply reading by 3)
//!   GPIO22 -> SK6812 data (via 470R), LED Vdd from 3V3
//!
//! API targets esp-idf-hal ~0.44/0.45. The ADC oneshot + WS2812 crate APIs have
//! churned across versions; the spots most likely to need a tweak are flagged with
//! `// VERSION:` comments. Logic is the part worth keeping.

use esp_idf_hal::delay::FreeRtos;
use esp_idf_hal::gpio::{Output, PinDriver};
use esp_idf_hal::ledc::{config::TimerConfig, LedcDriver, LedcTimerDriver, Resolution};
use esp_idf_hal::units::FromValueType;

// =====================================================================
// servo
// =====================================================================
pub mod servo {
    use super::*;
    use esp_idf_hal::gpio::Pin;

    /// Pulse width endpoints. Matches the repo's mapping:
    /// 90 deg = closed = ~1.0 ms, 180 deg = open = ~2.0 ms.
    const PERIOD_MS: f32 = 20.0; // 50 Hz
    const MIN_PULSE_MS: f32 = 1.0; // 90 deg
    const MAX_PULSE_MS: f32 = 2.0; // 180 deg
    const MIN_ANGLE: f32 = 90.0;
    const MAX_ANGLE: f32 = 180.0;

    /// Let the rail settle + servo energise before commanding a position.
    const POWER_SETTLE_MS: u32 = 50;
    /// Default travel budget. Worst case 90->180 on an SG90 is ~300 ms; pad it.
    const TRAVEL_MS: u32 = 500;
    /// Optional dwell at target before cutting power.
    const HOLD_MS: u32 = 100;

    pub struct Servo<'d, EN: Pin> {
        pwm: LedcDriver<'d>,
        enable: PinDriver<'d, EN, Output>,
        max_duty: u32,
    }

    impl<'d, EN: Pin> Servo<'d, EN> {
        /// `timer`/`channel` come from `peripherals.ledc.*`, `sig` is GPIO2,
        /// `enable` is an output PinDriver on GPIO21 (already `PinDriver::output`).
        pub fn new(
            timer: impl esp_idf_hal::peripheral::Peripheral<P = impl esp_idf_hal::ledc::LedcTimer>
                + 'd,
            channel: impl esp_idf_hal::peripheral::Peripheral<P = impl esp_idf_hal::ledc::LedcChannel>
                + 'd,
            sig: impl esp_idf_hal::peripheral::Peripheral<P = impl esp_idf_hal::gpio::OutputPin>
                + 'd,
            enable: PinDriver<'d, EN, Output>,
        ) -> anyhow::Result<Self> {
            let timer_cfg = TimerConfig::new()
                .frequency(50.Hz())
                .resolution(Resolution::Bits14); // 16383 counts over 20 ms
            let timer = LedcTimerDriver::new(timer, &timer_cfg)?;
            let pwm = LedcDriver::new(channel, &timer, sig)?;
            let max_duty = pwm.get_max_duty();
            Ok(Self { pwm, enable, max_duty })
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
        /// If your louver back-drives the gear, drop the final `power_off()`
        /// (servo keeps holding torque at the cost of ~10 mA continuous).
        pub fn move_to(&mut self, angle: f32) -> anyhow::Result<()> {
            self.power_on()?;
            FreeRtos::delay_ms(POWER_SETTLE_MS);

            self.pwm.set_duty(self.angle_to_duty(angle))?;
            self.pwm.enable()?;

            FreeRtos::delay_ms(TRAVEL_MS + HOLD_MS);

            // Stop the pulse train, then cut VCC.
            self.pwm.set_duty(0)?;
            self.pwm.disable()?;
            self.power_off()?;
            Ok(())
        }

        fn power_on(&mut self) -> anyhow::Result<()> {
            self.enable.set_high()?; // GPIO HIGH -> 2N7002 on -> P-FET on -> servo VCC live
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
    use esp_idf_hal::adc::attenuation::DB_11; // VERSION: renamed DB_12 in newer esp-idf
    use esp_idf_hal::adc::oneshot::config::AdcChannelConfig;
    use esp_idf_hal::adc::oneshot::{AdcChannelDriver, AdcDriver};
    use esp_idf_hal::adc::Adc;
    use esp_idf_hal::gpio::ADCPin;
    use esp_idf_hal::peripheral::Peripheral;

    /// Divider ratio (2M top / 1M bottom => tap = Vpack / 3).
    const DIVIDER: f32 = 3.0;
    const SAMPLES: usize = 16;

    /// 4-cell NiMH thresholds (pack mV). NiMH discharge is very flat, so treat
    /// this as a coarse "where am I" gauge, not a true fuel gauge.
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
                calibration: true, // VERSION: some versions use `Calibration::Curve`/enum
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
// indicator  (SK6812 single LED)
// =====================================================================
//
// One LED, several jobs, in priority order:
//   1. Identify    — "find this vent" among N installed vents. This is the
//                     primary use case and always wins: it's the one event
//                     a person is actively staring at the hardware for.
//   2. Install      — pairing/commissioning feedback. The device isn't on
//                     battery-conservation duty yet during setup, so this
//                     can be more liberal (pulsing, not just on-demand).
//   3. Command result — a brief on-demand blink confirming "this vent just
//                     did what it was told", useful with multiple vents
//                     so you can see which one responded to a command.
//   4. Battery      — on-demand colour after a move or an explicit query.
//                     Lowest priority: it's ambient health info, not
//                     something anyone is actively watching for.
// Nothing is ever left lit continuously — that's the on-demand battery
// budget from the power architecture doc.
pub mod indicator {
    use super::battery::State;
    use esp_idf_hal::delay::FreeRtos;
    use smart_leds::{SmartLedsWrite, RGB8};
    use std::iter::once;
    use ws2812_esp32_rmt_driver::Ws2812Esp32Rmt;

    // Dim colours — this LED sits on a battery, no need for full brightness.
    const OFF: RGB8 = RGB8 { r: 0, g: 0, b: 0 };
    const GREEN: RGB8 = RGB8 { r: 0, g: 24, b: 0 };
    const AMBER: RGB8 = RGB8 { r: 28, g: 14, b: 0 };
    const RED: RGB8 = RGB8 { r: 30, g: 0, b: 0 };
    const BLUE: RGB8 = RGB8 { r: 0, g: 0, b: 40 }; // identify
    const WHITE: RGB8 = RGB8 { r: 16, g: 16, b: 16 }; // installing / pairing

    /// What the LED is being asked to communicate. Variants are listed in
    /// priority order; if you need to layer events (e.g. a command result
    /// arrives mid-identify), let Identify finish first — it's the one the
    /// installer is actively looking at.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum Event {
        /// "Find this vent" — from the app, the /device/identity handler,
        /// or the Matter Identify cluster.
        Identify,
        /// Commissioning/pairing progress, shown during install only.
        Install(InstallState),
        /// A command just finished; confirms which physical vent reacted.
        CommandResult { ok: bool },
        /// Battery level, shown after a move or on an explicit query.
        Battery(State),
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum InstallState {
        /// Booting, not yet commissioned.
        AwaitingCommission,
        /// BLE advertising for commissioning.
        Pairing,
        /// Commissioning succeeded; joined the Matter fabric.
        Commissioned,
        /// Commissioning failed.
        Error,
    }

    pub struct Indicator<'d> {
        ws: Ws2812Esp32Rmt<'d>,
    }

    impl<'d> Indicator<'d> {
        /// VERSION: constructor signature varies by crate version. Common forms:
        ///   Ws2812Esp32Rmt::new(peripherals.rmt.channel0, pins.gpio22)?
        ///   Ws2812Esp32Rmt::new(0u32, 22u32)?            (older)
        pub fn new(
            channel: impl esp_idf_hal::peripheral::Peripheral<P = impl esp_idf_hal::rmt::RmtChannel>
                + 'd,
            pin: impl esp_idf_hal::peripheral::Peripheral<P = impl esp_idf_hal::gpio::OutputPin>
                + 'd,
        ) -> anyhow::Result<Self> {
            let ws = Ws2812Esp32Rmt::new(channel, pin)?;
            Ok(Self { ws })
        }

        fn set(&mut self, c: RGB8) -> anyhow::Result<()> {
            self.ws.write(once(c))?;
            Ok(())
        }

        pub fn off(&mut self) -> anyhow::Result<()> {
            self.set(OFF)
        }

        /// Dispatch any indicator event to the right pattern. Blocking;
        /// spawn on a task if a caller can't afford to wait it out.
        pub fn show(&mut self, event: Event) -> anyhow::Result<()> {
            match event {
                Event::Identify => self.identify(4),
                Event::Install(state) => self.install(state),
                Event::CommandResult { ok } => self.command_result(ok),
                Event::Battery(state) => self.show_battery(state, 600),
            }
        }

        /// "Find this vent" — the primary use case. Call from the app's
        /// locate action, the CoAP /device/identity handler, or the Matter
        /// Identify cluster.
        pub fn identify(&mut self, blinks: u8) -> anyhow::Result<()> {
            for _ in 0..blinks {
                self.set(BLUE)?;
                FreeRtos::delay_ms(200);
                self.off()?;
                FreeRtos::delay_ms(200);
            }
            Ok(())
        }

        /// Commissioning/pairing feedback. Only relevant before a vent is
        /// deployed, so it's fine to be more liberal with on-time here.
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

        /// One short blink confirming a command landed (or didn't) on this
        /// physical vent — useful for telling vents apart while operating
        /// several from the app.
        fn command_result(&mut self, ok: bool) -> anyhow::Result<()> {
            self.set(if ok { GREEN } else { RED })?;
            FreeRtos::delay_ms(150);
            self.off()
        }

        /// Briefly show pack state, then go dark (LED-on-demand to save power).
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

// =====================================================================
// wiring example (delete — illustrative only)
// =====================================================================
//
// let p = esp_idf_hal::peripherals::Peripherals::take()?;
//
// let servo_en = PinDriver::output(p.pins.gpio21)?;     // default low => servo OFF
// let mut servo = servo::Servo::new(
//     p.ledc.timer0, p.ledc.channel0, p.pins.gpio2, servo_en,
// )?;
//
// let mut pack = battery::PackSense::new(p.adc1, p.pins.gpio1)?;
// let mut led  = indicator::Indicator::new(p.rmt.channel0, p.pins.gpio22)?;
//
// // On a "set position" command — blink confirms which vent reacted:
// let result = servo.move_to(180.0);     // open; servo powers down after travel
// led.show(indicator::Event::CommandResult { ok: result.is_ok() })?;
// result?;
//
// // On a poll / wake, only surface battery state if it's getting low:
// let st = pack.read_state()?;
// if st == battery::State::Critical { led.show(indicator::Event::Battery(st))?; }
//
// // On an identify command from the app — "find this vent":
// led.show(indicator::Event::Identify)?;
//
// // During commissioning (see identity.rs's is_first_boot / commissioning flow):
// led.show(indicator::Event::Install(indicator::InstallState::Pairing))?;
// led.show(indicator::Event::Install(indicator::InstallState::Commissioned))?;
