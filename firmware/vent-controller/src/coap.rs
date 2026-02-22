use crate::identity::DeviceIdentity;
use crate::state::VentStateMachine;
use crate::thread::ThreadManager;
use log::{info, warn};
use minicbor::{to_vec, Decoder};
use std::ffi::c_void;
use std::sync::Mutex;
use std::time::Instant;
use vent_protocol::*;

// --- FFI declarations for OpenThread CoAP (not in esp-idf-sys bindings) ---

#[repr(C)]
struct OtCoapOption {
    number: u16,
    length: u16,
}

#[repr(C)]
struct OtCoapOptionIterator {
    message: *const esp_idf_sys::otMessage,
    option: OtCoapOption,
    next_option_offset: u16,
}

// CoAP codes (OT_COAP_CODE macro: ((class & 0x7) << 5) | (detail & 0x1f))
const OT_COAP_CODE_GET: u32 = (0 << 5) | 1; // 0.01
const OT_COAP_CODE_PUT: u32 = (0 << 5) | 3; // 0.03
const OT_COAP_CODE_CONTENT: u32 = (2 << 5) | 5; // 2.05 = 69
const OT_COAP_CODE_CHANGED: u32 = (2 << 5) | 4; // 2.04 = 68
const OT_COAP_CODE_BAD_REQUEST: u32 = (4 << 5) | 0; // 4.00 = 128
const OT_COAP_CODE_NOT_FOUND: u32 = (4 << 5) | 4; // 4.04 = 132
const OT_COAP_CODE_INTERNAL_ERROR: u32 = (5 << 5) | 0; // 5.00 = 160

const OT_COAP_TYPE_ACKNOWLEDGMENT: u32 = 2;

const OT_COAP_OPTION_URI_PATH: u16 = 11;
const OT_COAP_OPTION_CONTENT_FORMAT_CBOR: u32 = 60;

extern "C" {
    fn otCoapStart(instance: *mut esp_idf_sys::otInstance, port: u16) -> esp_idf_sys::otError;
    fn otCoapSetDefaultHandler(
        instance: *mut esp_idf_sys::otInstance,
        handler: Option<
            unsafe extern "C" fn(
                *mut c_void,
                *mut esp_idf_sys::otMessage,
                *const esp_idf_sys::otMessageInfo,
            ),
        >,
        context: *mut c_void,
    );
    fn otCoapNewMessage(
        instance: *mut esp_idf_sys::otInstance,
        settings: *const esp_idf_sys::otMessageSettings,
    ) -> *mut esp_idf_sys::otMessage;
    fn otCoapMessageInitResponse(
        response: *mut esp_idf_sys::otMessage,
        request: *const esp_idf_sys::otMessage,
        typ: u32,  // otCoapType
        code: u32, // otCoapCode
    ) -> esp_idf_sys::otError;
    fn otCoapMessageGetCode(message: *const esp_idf_sys::otMessage) -> u32;
    fn otCoapMessageSetPayloadMarker(
        message: *mut esp_idf_sys::otMessage,
    ) -> esp_idf_sys::otError;
    fn otCoapMessageAppendContentFormatOption(
        message: *mut esp_idf_sys::otMessage,
        content_format: u32, // otCoapOptionContentFormat
    ) -> esp_idf_sys::otError;
    fn otCoapSendResponseWithParameters(
        instance: *mut esp_idf_sys::otInstance,
        message: *mut esp_idf_sys::otMessage,
        message_info: *const esp_idf_sys::otMessageInfo,
        tx_parameters: *const c_void, // otCoapTxParameters, NULL for defaults
    ) -> esp_idf_sys::otError;
    fn otCoapOptionIteratorInit(
        iterator: *mut OtCoapOptionIterator,
        message: *const esp_idf_sys::otMessage,
    ) -> esp_idf_sys::otError;
    fn otCoapOptionIteratorGetFirstOptionMatching(
        iterator: *mut OtCoapOptionIterator,
        option: u16,
    ) -> *const OtCoapOption;
    fn otCoapOptionIteratorGetNextOptionMatching(
        iterator: *mut OtCoapOptionIterator,
        option: u16,
    ) -> *const OtCoapOption;
    fn otCoapOptionIteratorGetOptionValue(
        iterator: *mut OtCoapOptionIterator,
        value: *mut c_void,
    ) -> esp_idf_sys::otError;
}

const FIRMWARE_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Shared application state accessible by CoAP handlers.
pub struct AppState {
    pub vent: VentStateMachine,
    pub identity: DeviceIdentity,
    pub thread: ThreadManager,
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

    // WAL: persist intent before moving so it survives power loss
    if let Err(e) = state.identity.write_ahead(clamped) {
        warn!("WAL write-ahead failed: {:?}", e);
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
    let identity = vent_protocol::DeviceIdentity {
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
        rssi: state.thread.get_rssi(),
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

// --- Shared state and CoAP callback ---

static APP_STATE: Mutex<Option<AppState>> = Mutex::new(None);

/// Access the shared AppState. Returns None if not yet initialized.
pub fn with_app_state<F, R>(f: F) -> Option<R>
where
    F: FnOnce(&mut AppState) -> R,
{
    let mut guard = APP_STATE.lock().unwrap();
    guard.as_mut().map(f)
}

/// Default CoAP request handler called by the OpenThread stack for all incoming requests.
unsafe extern "C" fn coap_default_handler(
    _context: *mut c_void,
    message: *mut esp_idf_sys::otMessage,
    message_info: *const esp_idf_sys::otMessageInfo,
) {
    let instance = esp_idf_sys::esp_openthread_get_instance();

    // 1. Extract URI path from options
    let mut path_buf = [0u8; 128];
    let mut path_len: usize = 0;

    let mut iterator: OtCoapOptionIterator = std::mem::zeroed();
    if otCoapOptionIteratorInit(&mut iterator, message) != 0 {
        warn!("CoAP: failed to init option iterator");
        send_error_response(instance, message, message_info, OT_COAP_CODE_BAD_REQUEST);
        return;
    }

    let opt = otCoapOptionIteratorGetFirstOptionMatching(&mut iterator, OT_COAP_OPTION_URI_PATH);
    if !opt.is_null() {
        let mut segment = [0u8; 64];
        let len = (*opt).length as usize;
        if len <= segment.len()
            && otCoapOptionIteratorGetOptionValue(&mut iterator, segment.as_mut_ptr() as *mut c_void) == 0
        {
            let copy_len = len.min(path_buf.len() - path_len);
            path_buf[path_len..path_len + copy_len].copy_from_slice(&segment[..copy_len]);
            path_len += copy_len;
        }

        // Get remaining URI-Path segments
        loop {
            let opt = otCoapOptionIteratorGetNextOptionMatching(&mut iterator, OT_COAP_OPTION_URI_PATH);
            if opt.is_null() {
                break;
            }
            let len = (*opt).length as usize;
            // Add separator
            if path_len < path_buf.len() {
                path_buf[path_len] = b'/';
                path_len += 1;
            }
            if len <= segment.len()
                && otCoapOptionIteratorGetOptionValue(&mut iterator, segment.as_mut_ptr() as *mut c_void) == 0
            {
                let copy_len = len.min(path_buf.len() - path_len);
                path_buf[path_len..path_len + copy_len].copy_from_slice(&segment[..copy_len]);
                path_len += copy_len;
            }
        }
    }

    let path = core::str::from_utf8(&path_buf[..path_len]).unwrap_or("");

    // 2. Get method code
    let code = otCoapMessageGetCode(message);
    let method = match code {
        OT_COAP_CODE_GET => CoapMethod::Get,
        OT_COAP_CODE_PUT => CoapMethod::Put,
        _ => {
            info!("CoAP: unsupported method code {}", code);
            send_error_response(instance, message, message_info, OT_COAP_CODE_BAD_REQUEST);
            return;
        }
    };

    // 3. Read payload
    let mut payload_buf = [0u8; 256];
    let offset = esp_idf_sys::otMessageGetOffset(message);
    let total_len = esp_idf_sys::otMessageGetLength(message);
    let payload_len = if total_len > offset {
        let len = (total_len - offset) as usize;
        let len = len.min(payload_buf.len());
        esp_idf_sys::otMessageRead(
            message,
            offset,
            payload_buf.as_mut_ptr() as *mut c_void,
            len as u16,
        );
        len
    } else {
        0
    };

    info!("CoAP: {} {}", match code { OT_COAP_CODE_GET => "GET", _ => "PUT" }, path);

    // 4. Route request
    let mut guard = APP_STATE.lock().unwrap();
    let response = match guard.as_mut() {
        Some(state) => route_request(state, path, method, &payload_buf[..payload_len]),
        None => {
            warn!("CoAP: AppState not initialized");
            CoapResponse::InternalError
        }
    };
    drop(guard);

    // 5. Build and send response
    let (resp_code, body) = match response {
        CoapResponse::Content(data) => (OT_COAP_CODE_CONTENT, Some(data)),
        CoapResponse::Changed(data) => (OT_COAP_CODE_CHANGED, Some(data)),
        CoapResponse::BadRequest => (OT_COAP_CODE_BAD_REQUEST, None),
        CoapResponse::NotFound => (OT_COAP_CODE_NOT_FOUND, None),
        CoapResponse::InternalError => (OT_COAP_CODE_INTERNAL_ERROR, None),
    };

    let resp_msg = otCoapNewMessage(instance, std::ptr::null());
    if resp_msg.is_null() {
        warn!("CoAP: failed to allocate response message");
        return;
    }

    if otCoapMessageInitResponse(resp_msg, message, OT_COAP_TYPE_ACKNOWLEDGMENT, resp_code) != 0 {
        warn!("CoAP: failed to init response");
        return;
    }

    if let Some(ref data) = body {
        otCoapMessageAppendContentFormatOption(resp_msg, OT_COAP_OPTION_CONTENT_FORMAT_CBOR);
        otCoapMessageSetPayloadMarker(resp_msg);
        esp_idf_sys::otMessageAppend(resp_msg, data.as_ptr() as *const c_void, data.len() as u16);
    }

    let err = otCoapSendResponseWithParameters(instance, resp_msg, message_info, std::ptr::null());
    if err != 0 {
        warn!("CoAP: failed to send response: {}", err);
    }
}

/// Send an error-only CoAP response (no body).
unsafe fn send_error_response(
    instance: *mut esp_idf_sys::otInstance,
    request: *mut esp_idf_sys::otMessage,
    message_info: *const esp_idf_sys::otMessageInfo,
    code: u32,
) {
    let resp = otCoapNewMessage(instance, std::ptr::null());
    if resp.is_null() {
        return;
    }
    if otCoapMessageInitResponse(resp, request, OT_COAP_TYPE_ACKNOWLEDGMENT, code) != 0 {
        return;
    }
    otCoapSendResponseWithParameters(instance, resp, message_info, std::ptr::null());
}

/// Register CoAP default handler and start the server.
pub fn register_coap_resources(app_state: AppState) -> Result<(), esp_idf_sys::EspError> {
    info!("Registering CoAP resources...");

    // Store app state for the callback
    {
        let mut guard = APP_STATE.lock().unwrap();
        *guard = Some(app_state);
    }

    unsafe {
        let instance = esp_idf_sys::esp_openthread_get_instance();
        otCoapStart(instance, 5683);
        otCoapSetDefaultHandler(instance, Some(coap_default_handler), std::ptr::null_mut());
    }

    info!("CoAP server started on port 5683");
    Ok(())
}
