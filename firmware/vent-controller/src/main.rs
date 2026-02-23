#[allow(dead_code)]
mod coap;
#[allow(dead_code)]
mod identity;
#[allow(dead_code)]
mod matter;
#[allow(dead_code)]
mod power;
#[allow(dead_code)]
mod servo;
#[allow(dead_code)]
mod state;
#[allow(dead_code)]
mod thread;

use coap::register_coap_resources;
use identity::DeviceIdentity;
use power::{PowerManager, PowerMode};
use servo::ServoDriver;
use state::{AppState, VentStateMachine};
use thread::{ThreadConfig, ThreadManager};
use vent_protocol::{PowerSource, ANGLE_CLOSED};

use esp_idf_hal::ledc::{config::TimerConfig, LedcDriver, LedcTimerDriver, Resolution};
use esp_idf_hal::peripherals::Peripherals;
use esp_idf_hal::prelude::*;
use esp_idf_svc::nvs::EspDefaultNvsPartition;
use log::{error, info, warn};
use std::thread::sleep;
use std::time::{Duration, Instant};

fn main() {
    // Initialize ESP-IDF logging and system
    esp_idf_svc::sys::link_patches();
    esp_idf_logger::init().expect("Failed to init logger");

    info!("Vent Controller v{}", env!("CARGO_PKG_VERSION"));
    info!("Wakeup cause: {}", PowerManager::wakeup_cause_str());

    // Initialize peripherals
    let peripherals = Peripherals::take().expect("Failed to take peripherals");
    let nvs_partition = EspDefaultNvsPartition::take().expect("Failed to init NVS");

    // Initialize device identity
    let mut device_id = DeviceIdentity::new(nvs_partition).expect("Failed to init identity");
    info!("EUI-64: {}", device_id.eui64());

    // Check first boot
    match device_id.is_first_boot() {
        Ok(true) => {
            info!("First boot detected — initializing defaults");
            if let Err(e) = device_id.mark_initialized() {
                warn!("Failed to mark initialized: {:?}", e);
            }
        }
        Ok(false) => info!("Device previously initialized"),
        Err(e) => warn!("Could not check boot status: {:?}", e),
    }

    // WAL recovery — check if previous move was committed
    let committed = device_id.is_committed().unwrap_or(true);
    let (initial_angle, pending_target) = if committed {
        // Normal boot: restore last checkpoint
        let angle = device_id
            .checkpoint_angle()
            .ok()
            .flatten()
            .unwrap_or(ANGLE_CLOSED);
        info!("Restoring checkpoint: {}°", angle);
        (angle, None)
    } else {
        // Uncommitted move: intent was written-ahead but never committed.
        // Restore the last checkpoint first (known-good position), then
        // replay the pending target to complete the interrupted move.
        let checkpoint = device_id
            .checkpoint_angle()
            .ok()
            .flatten()
            .unwrap_or(ANGLE_CLOSED);
        let pending = device_id.get_pending().ok().flatten();
        warn!(
            "WAL recovery: uncommitted move detected. Checkpoint: {}°, pending: {:?}",
            checkpoint, pending
        );
        (checkpoint, pending)
    };

    // Initialize servo via LEDC PWM
    let timer_config = TimerConfig::default()
        .frequency(50.Hz().into())
        .resolution(Resolution::Bits14);
    let timer = LedcTimerDriver::new(
        peripherals.ledc.timer0,
        &timer_config,
    )
    .expect("Failed to init LEDC timer");

    let ledc_driver = LedcDriver::new(
        peripherals.ledc.channel0,
        timer,
        peripherals.pins.gpio2, // SG90 signal pin (XIAO ESP32C6 D2)
    )
    .expect("Failed to init LEDC channel");

    let mut servo = ServoDriver::new(ledc_driver).expect("Failed to init servo");
    if let Err(e) = servo.set_angle(initial_angle) {
        error!("Failed to set initial servo angle: {:?}", e);
    }

    // Initialize state machine at last known position
    let mut vent_state = VentStateMachine::new(initial_angle);

    // If a pending target exists from an interrupted move, replay it
    if let Some(target) = pending_target {
        info!("Replaying interrupted command: target {}°", target);
        vent_state.set_target(target);
    }

    // Determine power mode from NVS (default: always-on)
    let power_mode = match device_id.get_power_mode() {
        Ok(Some(mode_str)) => {
            let poll_ms = device_id.get_poll_period().ok().flatten().unwrap_or(5000);
            let mode = PowerMode::from_nvs_str(&mode_str, poll_ms);
            info!("Power mode from NVS: {}", mode.as_str());
            mode
        }
        _ => {
            info!("Power mode: always_on (default)");
            PowerMode::AlwaysOn
        }
    };
    let power_mgr = PowerManager::new(power_mode);

    // Initialize Thread networking
    let mut thread_mgr = ThreadManager::new(ThreadConfig::default());
    if let Err(e) = thread_mgr.init() {
        error!("Failed to init Thread: {:?}", e);
    }

    // Configure SED if battery-powered
    if let Err(e) = power_mgr.configure_sed() {
        error!("Failed to configure SED mode: {:?}", e);
    }

    // Build app state and register CoAP resources (must happen before mainloop starts)
    let app_state = AppState {
        vent: vent_state,
        identity: device_id,
        thread: thread_mgr,
        start_time: Instant::now(),
        power_source: match power_mode {
            PowerMode::AlwaysOn => PowerSource::Usb,
            PowerMode::Sed { .. } => PowerSource::Battery,
        },
        poll_period_ms: power_mode.poll_period_ms(),
    };

    if let Err(e) = register_coap_resources(app_state) {
        error!("Failed to register CoAP resources: {:?}", e);
    }

    // Initialize Matter (creates node + Window Covering endpoint)
    matter::init();
    matter::start();
    matter::log_pairing_info();

    // Start the OpenThread event loop in a dedicated thread.
    // esp_openthread_launch_mainloop() is blocking — it processes radio
    // frames, Thread protocol events, and CoAP requests.
    std::thread::Builder::new()
        .name("openthread".into())
        .stack_size(8192)
        .spawn(|| {
            info!("OpenThread mainloop started");
            unsafe {
                esp_idf_sys::esp_openthread_launch_mainloop();
            }
            warn!("OpenThread mainloop exited");
        })
        .expect("Failed to spawn OpenThread task");

    info!("Vent controller running. Waiting for CoAP/Matter commands...");

    // Main loop: process servo steps and Thread events
    loop {
        let is_moving = state::with_app_state(|s| s.vent.is_moving()).unwrap_or(false);

        if is_moving {
            state::with_app_state(|s| s.vent.step());

            let current_angle = state::with_app_state(|s| s.vent.current_angle()).unwrap_or(ANGLE_CLOSED);
            if let Err(e) = servo.set_angle(current_angle) {
                error!("Servo step failed: {:?}", e);
            }
            sleep(Duration::from_millis(servo::STEP_DELAY_MS as u64));

            // Commit when movement completes: checkpoint angle + set WAL flag
            let still_moving = state::with_app_state(|s| s.vent.is_moving()).unwrap_or(false);
            if !still_moving {
                state::with_app_state(|s| {
                    let final_angle = s.vent.current_angle();
                    if let Err(e) = s.identity.commit(final_angle) {
                        error!("WAL commit failed: {:?}", e);
                    }
                    info!(
                        "Vent reached target: {}° ({}) — committed",
                        final_angle,
                        s.vent.state().as_str()
                    );

                    // Report final position to Matter fabric
                    matter::report_position(final_angle);
                    matter::report_operational_status(false);
                });
            }
        } else {
            // Idle — sleep briefly to yield CPU
            sleep(Duration::from_millis(100));
        }
    }
}
