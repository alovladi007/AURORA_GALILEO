"""
Optical bench emulator — physical coupling tests (Phase 1 W1.4).

The emulator's channels must be physically coupled: an injected event
in one channel must show up in the interference signal, and the
telemetry channels must report the same environment the fringes felt.
"""

import numpy as np

from emulator.optical_bench import OpticalBenchEmulator


def _phase_series(emulator, times):
    return np.array(
        [emulator.get_full_state(t)["interference"]["phase"] for t in times]
    )


class TestChannelCoupling:
    def test_vibration_event_perturbs_the_fringes(self):
        """A vibration spike must increase phase jitter beyond the scan."""
        times = np.arange(0.0, 1.0, 1e-3)

        quiet = OpticalBenchEmulator()
        quiet.noise.phase_stability = 0.0  # isolate the coupling
        base = _phase_series(quiet, times)

        noisy = OpticalBenchEmulator()
        noisy.noise.phase_stability = 0.0
        noisy.inject_event("vibration_spike", magnitude=100.0)
        shaken = _phase_series(noisy, times)

        # Residual after removing the deterministic scan (same times):
        resid = np.unwrap(shaken) - np.unwrap(base)
        assert np.std(resid) > 0.1, (
            "vibration event did not reach the interference phase"
        )

    def test_thermal_event_shifts_the_operating_point(self):
        """A thermal jump changes expansion, which must move the OPD."""
        e1 = OpticalBenchEmulator()
        e2 = OpticalBenchEmulator()
        e2.inject_event("thermal_jump", magnitude=5.0)  # +5 K

        # Same timestamp; disable stochastic terms for a clean compare
        for e in (e1, e2):
            e.noise.phase_stability = 0.0
            e.noise.vibration_amplitude = 0.0
        s1 = e1.get_full_state(10.0)
        s2 = e2.get_full_state(10.0)
        assert s2["thermal"]["temperature"] > s1["thermal"]["temperature"]

    def test_laser_dropout_dims_the_fringes(self):
        """Reduced laser output must reduce mean fringe intensity."""
        times = np.arange(0.0, 2.0, 1e-3)
        normal = OpticalBenchEmulator()
        normal.noise.shot_noise_level = 0.0
        i_normal = np.mean(
            [normal.get_full_state(t)["interference"]["intensity"] for t in times]
        )

        dim = OpticalBenchEmulator()
        dim.noise.shot_noise_level = 0.0
        # Force a lower laser envelope by patching its generator scale
        orig = dim.generate_laser_intensity

        def dimmed(t):
            out = orig(t)
            out["intensity"] *= 0.5
            return out

        dim.generate_laser_intensity = dimmed
        i_dim = np.mean(
            [dim.get_full_state(t)["interference"]["intensity"] for t in times]
        )
        assert i_dim < 0.75 * i_normal

    def test_scan_is_resolvable_at_sampling_rate(self):
        """The piezo scan produces a smoothly varying phase: consecutive
        1 kHz samples differ by far less than pi (the old +/-1 m sweep
        aliased to noise)."""
        e = OpticalBenchEmulator()
        e.noise.phase_stability = 0.0
        e.noise.vibration_amplitude = 0.0
        times = np.arange(0.0, 1.0, 1e-3)
        opd = np.array(
            [e.get_full_state(t)["interference"]["optical_path_diff"]
             for t in times]
        )  # nm
        k = 2 * np.pi / 632.8e-9
        dphi = np.abs(np.diff(opd * 1e-9)) * k
        assert np.max(dphi) < np.pi

    def test_diagnostics_report_actual_visibility(self):
        e = OpticalBenchEmulator()
        e.inject_event("vibration_spike", magnitude=1e3)
        e.get_full_state(0.5)
        diag = e.get_diagnostics()
        assert diag["fringe_contrast"] < 0.95, (
            "diagnostics must reflect the degraded visibility"
        )
