use log::{error, info, warn};
use std::ffi::c_void;
use vent_protocol::{ANGLE_CLOSED, ANGLE_OPEN};

// --- FFI declarations matching matter_bridge.h ---

type PositionCb = unsafe extern "C" fn(percent100ths: u16, ctx: *mut c_void);
type IdentifyCb = unsafe extern "C" fn(duration_s: u16, ctx: *mut c_void);

extern "C" {
    fn matter_bridge_init(
        position_cb: PositionCb,
        identify_cb: IdentifyCb,
        ctx: *mut c_void,
    ) -> i32;
    fn matter_bridge_start() -> i32;
    fn matter_bridge_update_position(percent100ths: u16);
    fn matter_bridge_update_operational_status(status: u8);
    fn matter_bridge_is_commissioned() -> bool;
    fn matter_bridge_get_pairing_code(buf: *mut u8, len: usize) -> i32;
    fn matter_bridge_get_qr_payload(buf: *mut u8, len: usize) -> i32;
}

// --- Angle <-> Matter percent100ths conversion ---
//
// Matter Window Covering uses percent100ths (0–10000):
//   0     = fully open  (vent angle 180°)
//   10000 = fully closed (vent angle 90°)
//
// Our servo angle range: 90° (closed) to 180° (open)

/// Convert servo angle (90–180) to Matter percent100ths (0–10000).
/// In Matter, 0% = open, 100% = closed.
pub fn angle_to_percent100ths(angle: u8) -> u16 {
    let clamped = angle.clamp(ANGLE_CLOSED, ANGLE_OPEN);
    let range = (ANGLE_OPEN - ANGLE_CLOSED) as u16; // 90
    let from_open = (ANGLE_OPEN - clamped) as u16;
    (from_open * 10000) / range
}

/// Convert Matter percent100ths (0–10000) to servo angle (90–180).
/// In Matter, 0% = open, 100% = closed.
pub fn percent100ths_to_angle(pct: u16) -> u8 {
    let clamped = pct.min(10000);
    let range = (ANGLE_OPEN - ANGLE_CLOSED) as u16; // 90
    let from_open = (clamped * range) / 10000;
    ANGLE_OPEN - from_open as u8
}

// --- Callbacks from Matter SDK (C context) ---

unsafe extern "C" fn on_position_change(percent100ths: u16, _ctx: *mut c_void) {
    let angle = percent100ths_to_angle(percent100ths);
    info!("Matter: position change -> {}° (pct100ths={})", angle, percent100ths);

    crate::state::with_app_state(|s| {
        // WAL: persist intent before moving
        if let Err(e) = s.identity.write_ahead(angle) {
            warn!("Matter: WAL write-ahead failed: {:?}", e);
            return;
        }
        let prev = s.vent.set_target(angle);
        info!("Matter: target set {}° -> {}°", prev, angle);
    });
}

unsafe extern "C" fn on_identify(duration_s: u16, _ctx: *mut c_void) {
    info!("Matter: identify requested for {}s", duration_s);
    // Identify implementation deferred to PR 9
}

// --- Public Rust API ---

/// Initialize the Matter node. Must be called after `init_app_state()`.
pub fn init() {
    info!("Initializing Matter...");
    let ret = unsafe {
        matter_bridge_init(on_position_change, on_identify, std::ptr::null_mut())
    };
    if ret != 0 {
        error!("Matter init failed: {}", ret);
    }
}

/// Start the Matter event loop.
pub fn start() {
    info!("Starting Matter...");
    let ret = unsafe { matter_bridge_start() };
    if ret != 0 {
        error!("Matter start failed: {}", ret);
    }
}

/// Report the current vent position to Matter fabric.
pub fn report_position(angle: u8) {
    let pct = angle_to_percent100ths(angle);
    unsafe { matter_bridge_update_position(pct) };
}

/// Report whether the vent is currently moving.
pub fn report_operational_status(is_moving: bool) {
    // WindowCovering OperationalStatus bitmap:
    // bits 0-1: global movement (0=stopped, 1=opening, 2=closing)
    let status: u8 = if is_moving { 1 } else { 0 };
    unsafe { matter_bridge_update_operational_status(status) };
}

/// Check if the device is commissioned into a Matter fabric.
pub fn is_commissioned() -> bool {
    unsafe { matter_bridge_is_commissioned() }
}

/// Log pairing info to serial console.
pub fn log_pairing_info() {
    let mut code_buf = [0u8; 32];
    let mut qr_buf = [0u8; 128];

    let code_ok = unsafe { matter_bridge_get_pairing_code(code_buf.as_mut_ptr(), code_buf.len()) };
    let qr_ok = unsafe { matter_bridge_get_qr_payload(qr_buf.as_mut_ptr(), qr_buf.len()) };

    if code_ok == 0 {
        let code = std::str::from_utf8(&code_buf)
            .unwrap_or("")
            .trim_end_matches('\0');
        info!("Manual pairing code: {}", code);
    }
    if qr_ok == 0 {
        let qr = std::str::from_utf8(&qr_buf)
            .unwrap_or("")
            .trim_end_matches('\0');
        info!("QR code payload: {}", qr);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_angle_to_percent100ths_open() {
        // 180° (fully open) -> 0% in Matter
        assert_eq!(angle_to_percent100ths(180), 0);
    }

    #[test]
    fn test_angle_to_percent100ths_closed() {
        // 90° (fully closed) -> 100% (10000) in Matter
        assert_eq!(angle_to_percent100ths(90), 10000);
    }

    #[test]
    fn test_angle_to_percent100ths_midpoint() {
        // 135° (half open) -> 50% (5000) in Matter
        assert_eq!(angle_to_percent100ths(135), 5000);
    }

    #[test]
    fn test_angle_to_percent100ths_clamp_low() {
        // Below 90° clamps to 90° -> 10000
        assert_eq!(angle_to_percent100ths(0), 10000);
    }

    #[test]
    fn test_angle_to_percent100ths_clamp_high() {
        // Above 180° clamps to 180° -> 0
        assert_eq!(angle_to_percent100ths(255), 0);
    }

    #[test]
    fn test_percent100ths_to_angle_open() {
        // 0% -> 180° (fully open)
        assert_eq!(percent100ths_to_angle(0), 180);
    }

    #[test]
    fn test_percent100ths_to_angle_closed() {
        // 10000 (100%) -> 90° (fully closed)
        assert_eq!(percent100ths_to_angle(10000), 90);
    }

    #[test]
    fn test_percent100ths_to_angle_midpoint() {
        // 5000 (50%) -> 135°
        assert_eq!(percent100ths_to_angle(5000), 135);
    }

    #[test]
    fn test_percent100ths_to_angle_clamp_over() {
        // >10000 clamps to 10000 -> 90°
        assert_eq!(percent100ths_to_angle(20000), 90);
    }

    #[test]
    fn test_roundtrip_open() {
        assert_eq!(percent100ths_to_angle(angle_to_percent100ths(180)), 180);
    }

    #[test]
    fn test_roundtrip_closed() {
        assert_eq!(percent100ths_to_angle(angle_to_percent100ths(90)), 90);
    }

    #[test]
    fn test_roundtrip_partial() {
        // Some angles may not round-trip perfectly due to integer division,
        // but should be within 1°
        for angle in 90..=180 {
            let pct = angle_to_percent100ths(angle);
            let back = percent100ths_to_angle(pct);
            assert!(
                (back as i16 - angle as i16).abs() <= 1,
                "angle {} -> pct {} -> back {}", angle, pct, back
            );
        }
    }
}
