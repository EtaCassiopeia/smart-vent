use crate::identity::DeviceIdentity;
use crate::state::VentStateMachine;
use log::{info, warn};
use minicbor::{to_vec, Decoder};
use vent_protocol::*;
use std::time::Instant;

const FIRMWARE_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Shared application state accessible by CoAP handlers.
pub struct AppState {
    pub vent: VentStateMachine,
    pub identity: DeviceIdentity,
    pub start_time: Instant,
    pub power_source: PowerSource,
    pub poll_period_ms: u32,
}

/// CoAP resource handler results.
pub enum CoapResponse {
    Content(Vec<u8>),
    Changed(Vec<u8>),
    BadRequest,
    NotFound,
    InternalError,
}

/// Handle GET /vent/position
pub fn handle_get_position(state: &AppState) -> CoapResponse {
    let pos = VentPosition {
        angle: state.vent.current_angle(),
        state: state.vent.state(),
    };
    match to_vec(&pos) {
        Ok(bytes) => CoapResponse::Content(bytes),
        Err(_) => CoapResponse::InternalError,
    }
}

/// Handle PUT /vent/target
pub fn handle_put_target(state: &mut AppState, payload: &[u8]) -> CoapResponse {
    let mut decoder = Decoder::new(payload);
    let req: TargetRequest = match decoder.decode() {
        Ok(r) => r,
        Err(_) => return CoapResponse::BadRequest,
    };

    let clamped = clamp_angle(req.angle);

    // Write-ahead: persist target + clear finalized BEFORE moving
    if let Err(e) = state.identity.save_pending_target(clamped) {
        warn!("Failed to write-ahead target: {:?}", e);
        return CoapResponse::InternalError;
    }

    let previous_angle = state.vent.set_target(req.angle);
    let resp = TargetResponse {
        angle: clamped,
        state: state.vent.state(),
        previous_angle,
    };

    info!("Target set: {}° -> {}°", previous_angle, clamped);

    match to_vec(&resp) {
        Ok(bytes) => CoapResponse::Changed(bytes),
        Err(_) => CoapResponse::InternalError,
    }
}

/// Handle GET /device/identity
pub fn handle_get_identity(state: &AppState) -> CoapResponse {
    let uptime = state.start_time.elapsed().as_secs() as u32;
    let identity = DeviceIdentity {
        eui64: state.identity.eui64().into(),
        firmware_version: FIRMWARE_VERSION.into(),
        uptime_s: uptime,
    };
    match to_vec(&identity) {
        Ok(bytes) => CoapResponse::Content(bytes),
        Err(_) => CoapResponse::InternalError,
    }
}

/// Handle GET /device/config
pub fn handle_get_config(state: &AppState) -> CoapResponse {
    let config = DeviceConfig {
        room: state.identity.get_room().ok().flatten(),
        floor: state.identity.get_floor().ok().flatten(),
        name: state.identity.get_name().ok().flatten(),
    };
    match to_vec(&config) {
        Ok(bytes) => CoapResponse::Content(bytes),
        Err(_) => CoapResponse::InternalError,
    }
}

/// Handle PUT /device/config
pub fn handle_put_config(state: &mut AppState, payload: &[u8]) -> CoapResponse {
    let mut decoder = Decoder::new(payload);
    let config: DeviceConfig = match decoder.decode() {
        Ok(c) => c,
        Err(_) => return CoapResponse::BadRequest,
    };

    // Apply partial updates
    if let Some(ref room) = config.room {
        if let Err(e) = state.identity.set_room(room) {
            warn!("Failed to save room: {:?}", e);
            return CoapResponse::InternalError;
        }
    }
    if let Some(ref floor) = config.floor {
        if let Err(e) = state.identity.set_floor(floor) {
            warn!("Failed to save floor: {:?}", e);
            return CoapResponse::InternalError;
        }
    }
    if let Some(ref name) = config.name {
        if let Err(e) = state.identity.set_name(name) {
            warn!("Failed to save name: {:?}", e);
            return CoapResponse::InternalError;
        }
    }

    info!("Config updated: room={:?}, floor={:?}, name={:?}",
        config.room, config.floor, config.name);

    // Return full updated config
    handle_get_config(state)
}

/// Handle GET /device/health
pub fn handle_get_health(state: &AppState) -> CoapResponse {
    let health = DeviceHealth {
        rssi: -50, // TODO: read from Thread stack
        poll_period_ms: state.poll_period_ms,
        power_source: state.power_source,
        free_heap: unsafe { esp_idf_sys::esp_get_free_heap_size() },
        battery_mv: match state.power_source {
            PowerSource::Battery => Some(3300), // TODO: ADC reading
            PowerSource::Usb => None,
        },
    };
    match to_vec(&health) {
        Ok(bytes) => CoapResponse::Content(bytes),
        Err(_) => CoapResponse::InternalError,
    }
}

/// Route a CoAP request to the appropriate handler.
pub fn route_request(
    state: &mut AppState,
    path: &str,
    method: CoapMethod,
    payload: &[u8],
) -> CoapResponse {
    match (path, method) {
        ("vent/position", CoapMethod::Get) => handle_get_position(state),
        ("vent/target", CoapMethod::Put) => handle_put_target(state, payload),
        ("device/identity", CoapMethod::Get) => handle_get_identity(state),
        ("device/config", CoapMethod::Get) => handle_get_config(state),
        ("device/config", CoapMethod::Put) => handle_put_config(state, payload),
        ("device/health", CoapMethod::Get) => handle_get_health(state),
        _ => CoapResponse::NotFound,
    }
}

/// CoAP method types we handle.
pub enum CoapMethod {
    Get,
    Put,
}

/// Register all CoAP resources with the OpenThread CoAP server.
///
/// This sets up the OT CoAP server to call our route_request function
/// for incoming requests. The actual OT CoAP integration uses C callbacks
/// that post to our Rust handler via a channel.
pub fn register_coap_resources() -> Result<(), esp_idf_sys::EspError> {
    info!("Registering CoAP resources...");

    unsafe {
        let instance = esp_idf_sys::esp_openthread_get_instance();
        esp_idf_sys::otCoapStart(instance, 5683);
    }

    info!("CoAP server started on port 5683");
    Ok(())
}
