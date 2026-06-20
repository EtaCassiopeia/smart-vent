#![cfg_attr(not(feature = "std"), no_std)]

/// Vent angle limits.
pub const ANGLE_CLOSED: u8 = 90;
pub const ANGLE_OPEN: u8 = 180;

/// Vent operating states.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VentState {
    Open,
    Closed,
    Partial,
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

/// Power source variants.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PowerSource {
    Usb,
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

/// Clamp angle to valid range [ANGLE_CLOSED, ANGLE_OPEN].
pub fn clamp_angle(angle: u8) -> u8 {
    angle.clamp(ANGLE_CLOSED, ANGLE_OPEN)
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
