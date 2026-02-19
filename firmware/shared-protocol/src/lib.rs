#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

use alloc::string::String;
use minicbor::{Decode, Encode};

/// Vent angle limits.
pub const ANGLE_CLOSED: u8 = 90;
pub const ANGLE_OPEN: u8 = 180;

/// Vent operating states.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Encode, Decode)]
#[cbor(index_only)]
pub enum VentState {
    #[n(0)]
    Open,
    #[n(1)]
    Closed,
    #[n(2)]
    Partial,
    #[n(3)]
    Moving,
}

impl VentState {
    pub fn as_str(&self) -> &'static str {
        match self {
            VentState::Open => "open",
            VentState::Closed => "closed",
            VentState::Partial => "partial",
            VentState::Moving => "moving",
        }
    }

    pub fn from_angle(angle: u8) -> Self {
        match angle {
            ANGLE_CLOSED => VentState::Closed,
            ANGLE_OPEN => VentState::Open,
            _ => VentState::Partial,
        }
    }
}

/// Response for GET /vent/position.
#[derive(Debug, Clone, Encode, Decode)]
pub struct VentPosition {
    #[n(0)]
    pub angle: u8,
    #[n(1)]
    pub state: VentState,
}

/// Request for PUT /vent/target.
#[derive(Debug, Clone, Encode, Decode)]
pub struct TargetRequest {
    #[n(0)]
    pub angle: u8,
}

/// Response for PUT /vent/target.
#[derive(Debug, Clone, Encode, Decode)]
pub struct TargetResponse {
    #[n(0)]
    pub angle: u8,
    #[n(1)]
    pub state: VentState,
    #[n(2)]
    pub previous_angle: u8,
}

/// Response for GET /device/identity.
#[derive(Debug, Clone, Encode, Decode)]
pub struct DeviceIdentity {
    #[n(0)]
    pub eui64: String,
    #[n(1)]
    pub firmware_version: String,
    #[n(2)]
    pub uptime_s: u32,
}

/// GET/PUT /device/config.
#[derive(Debug, Clone, Default, Encode, Decode)]
pub struct DeviceConfig {
    #[n(0)]
    pub room: Option<String>,
    #[n(1)]
    pub floor: Option<String>,
    #[n(2)]
    pub name: Option<String>,
}

/// Power source variants.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Encode, Decode)]
#[cbor(index_only)]
pub enum PowerSource {
    #[n(0)]
    Usb,
    #[n(1)]
    Battery,
}

impl PowerSource {
    pub fn as_str(&self) -> &'static str {
        match self {
            PowerSource::Usb => "usb",
            PowerSource::Battery => "battery",
        }
    }
}

/// Response for GET /device/health.
#[derive(Debug, Clone, Encode, Decode)]
pub struct DeviceHealth {
    #[n(0)]
    pub rssi: i8,
    #[n(1)]
    pub poll_period_ms: u32,
    #[n(2)]
    pub power_source: PowerSource,
    #[n(3)]
    pub free_heap: u32,
    #[n(4)]
    pub battery_mv: Option<u16>,
}

/// Clamp angle to valid range [ANGLE_CLOSED, ANGLE_OPEN].
pub fn clamp_angle(angle: u8) -> u8 {
    angle.clamp(ANGLE_CLOSED, ANGLE_OPEN)
}

#[cfg(test)]
mod tests {
    use super::*;
    use minicbor::{decode, to_vec};

    #[test]
    fn test_vent_state_from_angle() {
        assert_eq!(VentState::from_angle(90), VentState::Closed);
        assert_eq!(VentState::from_angle(180), VentState::Open);
        assert_eq!(VentState::from_angle(135), VentState::Partial);
    }

    #[test]
    fn test_clamp_angle() {
        assert_eq!(clamp_angle(0), ANGLE_CLOSED);
        assert_eq!(clamp_angle(90), 90);
        assert_eq!(clamp_angle(135), 135);
        assert_eq!(clamp_angle(180), 180);
        assert_eq!(clamp_angle(255), ANGLE_OPEN);
    }

    #[test]
    fn test_vent_position_cbor_roundtrip() {
        let pos = VentPosition {
            angle: 135,
            state: VentState::Partial,
        };
        let bytes = to_vec(&pos).unwrap();
        let decoded: VentPosition = decode(&bytes).unwrap();
        assert_eq!(decoded.angle, 135);
        assert_eq!(decoded.state, VentState::Partial);
    }

    #[test]
    fn test_target_request_cbor_roundtrip() {
        let req = TargetRequest { angle: 120 };
        let bytes = to_vec(&req).unwrap();
        let decoded: TargetRequest = decode(&bytes).unwrap();
        assert_eq!(decoded.angle, 120);
    }

    #[test]
    fn test_device_config_cbor_roundtrip() {
        let config = DeviceConfig {
            room: Some("bedroom".into()),
            floor: Some("2".into()),
            name: None,
        };
        let bytes = to_vec(&config).unwrap();
        let decoded: DeviceConfig = decode(&bytes).unwrap();
        assert_eq!(decoded.room.as_deref(), Some("bedroom"));
        assert_eq!(decoded.floor.as_deref(), Some("2"));
        assert!(decoded.name.is_none());
    }
}
