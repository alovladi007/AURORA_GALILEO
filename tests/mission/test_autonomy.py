"""
Station-keeping autonomy acceptance tests (Phase 4 W4.3).

The Gate 4 criterion: the autonomy runs for 24 simulated hours without
operator intervention, holds the formation box, and accounts for every
newton-second of fuel.
"""

import numpy as np
import pytest

from mission.autonomy import AutonomyConfig, StationKeepingAutonomy

DAY_S = 24 * 3600.0


class TestDisturbanceReality:
    def test_uncontrolled_formation_drifts_out(self):
        """Sanity: without autonomy the differential drag genuinely
        breaks the formation (otherwise the controller proves nothing)."""
        cfg = AutonomyConfig(deadband_m=1e12)  # never engage
        result = StationKeepingAutonomy(cfg).run(DAY_S)
        assert result.total_delta_v == 0.0
        assert result.max_pos_error_m > 200.0, (
            f"disturbance too weak to matter: max error "
            f"{result.max_pos_error_m:.0f} m"
        )


class TestAutonomyHoldsTheBox:
    @pytest.fixture(scope="class")
    def day_run(self):
        return StationKeepingAutonomy(AutonomyConfig()).run(DAY_S)

    def test_24h_without_intervention(self, day_run):
        """Position error must stay bounded near the dead-band for the
        whole day (transients above the 50 m dead-band are allowed
        while a burn campaign brings the error back)."""
        assert day_run.max_pos_error_m < 3.0 * 50.0, (
            f"formation lost: max error {day_run.max_pos_error_m:.0f} m"
        )
        # It ends the day inside the dead-band
        final_err = float(np.linalg.norm(day_run.states[-1, :3]))
        assert final_err < 50.0

    def test_deadband_autonomy_coasts_between_burns(self, day_run):
        """Burns must be episodic — the autonomy coasts most of the
        time instead of thrusting continuously."""
        duty_cycle = float(np.mean(day_run.controlled))
        assert 0.0 < duty_cycle < 0.5, (
            f"thrust duty cycle {duty_cycle:.0%} — dead-band logic broken"
        )
        assert len(day_run.burns) >= 1

    def test_fuel_accounting(self, day_run):
        """Every burn's delta-v sums to the total; total is positive,
        physically sensible, and within budget."""
        assert not day_run.budget_exceeded
        assert day_run.total_delta_v > 0.0
        assert day_run.total_delta_v < AutonomyConfig().delta_v_budget
        by_burns = sum(b.delta_v for b in day_run.burns)
        assert by_burns == pytest.approx(day_run.total_delta_v, rel=1e-9)
        # Order-of-magnitude physics: countering a ~2e-7 m/s^2
        # disturbance for a day costs at least a*T ~ 1.7 cm/s
        assert day_run.total_delta_v > 0.005

    def test_more_disturbance_costs_more_fuel(self):
        low = StationKeepingAutonomy(
            AutonomyConfig(differential_drag=1e-7)).run(DAY_S / 2)
        high = StationKeepingAutonomy(
            AutonomyConfig(differential_drag=4e-7)).run(DAY_S / 2)
        assert high.total_delta_v > low.total_delta_v


class TestFuelBudgetFDIR:
    def test_budget_exhaustion_stops_thrusting_and_flags(self):
        """FDIR: when the delta-v budget runs out the autonomy must stop
        commanding thrust and raise the flag — never silently overspend."""
        cfg = AutonomyConfig(delta_v_budget=0.002,  # deliberately tiny
                             differential_drag=4e-7)
        result = StationKeepingAutonomy(cfg).run(DAY_S / 2)
        assert result.budget_exceeded
        assert result.total_delta_v <= cfg.delta_v_budget + 1e-9
        # after exhaustion the error grows again (honest consequence)
        assert result.max_pos_error_m > cfg.deadband_m
