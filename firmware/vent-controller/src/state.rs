use crate::identity::DeviceIdentity;
use crate::thread::ThreadManager;
use std::sync::Mutex;
use std::time::Instant;
use vent_protocol::{clamp_angle, PowerSource, VentState};

/// Shared application state accessible by CoAP and Matter handlers.
pub struct AppState {
    pub vent: VentStateMachine,
    pub identity: DeviceIdentity,
    pub thread: ThreadManager,
    pub start_time: Instant,
    pub power_source: PowerSource,
    pub poll_period_ms: u32,
    /// True when the servo is doing an identify wiggle.
    pub identify_mode: bool,
    /// Angle to restore after identify completes.
    pub identify_restore_angle: Option<u8>,
}

static APP_STATE: Mutex<Option<AppState>> = Mutex::new(None);

/// Initialize the shared AppState. Must be called once before any handler runs.
pub fn init_app_state(state: AppState) {
    let mut guard = APP_STATE.lock().unwrap();
    *guard = Some(state);
}

/// Access the shared AppState. Returns None if not yet initialized.
pub fn with_app_state<F, R>(f: F) -> Option<R>
where
    F: FnOnce(&mut AppState) -> R,
{
    let mut guard = APP_STATE.lock().unwrap();
    guard.as_mut().map(f)
}

/// Vent state machine managing position and transitions.
pub struct VentStateMachine {
    current_angle: u8,
    target_angle: u8,
}

impl VentStateMachine {
    pub fn new(initial_angle: u8) -> Self {
        let angle = clamp_angle(initial_angle);
        Self {
            current_angle: angle,
            target_angle: angle,
        }
    }

    pub fn current_angle(&self) -> u8 {
        self.current_angle
    }

    pub fn target_angle(&self) -> u8 {
        self.target_angle
    }

    pub fn state(&self) -> VentState {
        if self.current_angle != self.target_angle {
            VentState::Moving
        } else {
            VentState::from_angle(self.current_angle)
        }
    }

    /// Set a new target angle. Returns the previous angle.
    pub fn set_target(&mut self, angle: u8) -> u8 {
        let prev = self.current_angle;
        self.target_angle = clamp_angle(angle);
        prev
    }

    /// Advance one step toward the target. Returns true if still moving.
    pub fn step(&mut self) -> bool {
        if self.current_angle < self.target_angle {
            self.current_angle += 1;
            true
        } else if self.current_angle > self.target_angle {
            self.current_angle -= 1;
            true
        } else {
            false
        }
    }

    /// Check if the vent is currently moving toward a target.
    pub fn is_moving(&self) -> bool {
        self.current_angle != self.target_angle
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vent_protocol::{ANGLE_CLOSED, ANGLE_OPEN};

    #[test]
    fn test_initial_state_closed() {
        let sm = VentStateMachine::new(ANGLE_CLOSED);
        assert_eq!(sm.current_angle(), 90);
        assert_eq!(sm.state(), VentState::Closed);
        assert!(!sm.is_moving());
    }

    #[test]
    fn test_initial_state_open() {
        let sm = VentStateMachine::new(ANGLE_OPEN);
        assert_eq!(sm.current_angle(), 180);
        assert_eq!(sm.state(), VentState::Open);
    }

    #[test]
    fn test_clamps_out_of_range() {
        let sm = VentStateMachine::new(0);
        assert_eq!(sm.current_angle(), ANGLE_CLOSED);

        let sm = VentStateMachine::new(255);
        assert_eq!(sm.current_angle(), ANGLE_OPEN);
    }

    #[test]
    fn test_set_target_returns_previous() {
        let mut sm = VentStateMachine::new(90);
        let prev = sm.set_target(180);
        assert_eq!(prev, 90);
        assert_eq!(sm.state(), VentState::Moving);
    }

    #[test]
    fn test_step_moves_toward_target() {
        let mut sm = VentStateMachine::new(90);
        sm.set_target(93);

        assert!(sm.step());
        assert_eq!(sm.current_angle(), 91);
        assert!(sm.step());
        assert_eq!(sm.current_angle(), 92);
        assert!(sm.step());
        assert_eq!(sm.current_angle(), 93);
        assert!(!sm.step()); // reached target
        assert_eq!(sm.state(), VentState::Partial);
    }

    #[test]
    fn test_step_moves_down() {
        let mut sm = VentStateMachine::new(95);
        sm.set_target(90);

        for _ in 0..5 {
            assert!(sm.step());
        }
        assert!(!sm.step());
        assert_eq!(sm.current_angle(), 90);
        assert_eq!(sm.state(), VentState::Closed);
    }

    #[test]
    fn test_full_open_close_cycle() {
        let mut sm = VentStateMachine::new(90);
        sm.set_target(180);

        // Step all the way to open
        while sm.step() {}
        assert_eq!(sm.current_angle(), 180);
        assert_eq!(sm.state(), VentState::Open);

        // Now close
        sm.set_target(90);
        while sm.step() {}
        assert_eq!(sm.current_angle(), 90);
        assert_eq!(sm.state(), VentState::Closed);
    }

    #[test]
    fn test_target_clamped() {
        let mut sm = VentStateMachine::new(90);
        sm.set_target(0);
        assert_eq!(sm.target_angle(), ANGLE_CLOSED);

        sm.set_target(255);
        assert_eq!(sm.target_angle(), ANGLE_OPEN);
    }
}
