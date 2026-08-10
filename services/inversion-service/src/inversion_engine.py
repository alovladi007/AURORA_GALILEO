"""
Inversion Engine
================

Real gravity inversion engine for the Inversion Service. Wraps the scientific
solvers (Tikhonov regularization, Gauss-Newton, Bayesian MAP) with a forward
gravity operator, progress tracking and result serialization.

This module is self-contained (vendored solver implementations) so the service
container builds without needing the repository-root ``/inversion`` package on
the build context. The numerical methods mirror ``inversion/solvers.py``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Optional multiscale solver
try:
    from src.multiscale_solver import MultiscaleInversionEngine
    _HAS_MULTISCALE = True
except ImportError:
    _HAS_MULTISCALE = False
    logger.warning("Multiscale solver not available (pywavelets not installed)")


# ---------------------------------------------------------------------------
# Forward gravity operator
# ---------------------------------------------------------------------------
def build_point_mass_operator(
    grid_shape: tuple[int, int],
    n_observations: int,
    observation_height: float = 1.0,
    cell_size: float = 1.0,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Build a linear forward operator G mapping subsurface density anomalies
    to surface gravity observations using a point-mass (Newtonian) kernel.

    The kernel for a point mass at depth ``z`` measured at horizontal offset
    ``r`` is ``G * dz / (r^2 + z^2)^{3/2}`` (vertical component of gravity).

    Parameters
    ----------
    grid_shape : (n_rows, n_cols)
        Subsurface model grid dimensions.
    n_observations : int
        Number of surface observation points.
    observation_height : float
        Vertical separation between observation plane and the source layer.
    cell_size : float
        Physical size of a grid cell (used for spatial coordinates).
    rng : numpy Generator, optional
        Random generator for observation placement (deterministic if seeded).

    Returns
    -------
    G : ndarray, shape (n_observations, n_model)
        Forward operator matrix.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    n_rows, n_cols = grid_shape
    n_model = n_rows * n_cols

    # Source cell centre coordinates (z = observation_height below the plane).
    xs, ys = np.meshgrid(
        np.arange(n_cols) * cell_size,
        np.arange(n_rows) * cell_size,
    )
    source_xy = np.column_stack([xs.ravel(), ys.ravel()])

    # Observation points sampled across the same horizontal extent.
    obs_x = rng.uniform(0, max(n_cols - 1, 1) * cell_size, n_observations)
    obs_y = rng.uniform(0, max(n_rows - 1, 1) * cell_size, n_observations)
    obs_xy = np.column_stack([obs_x, obs_y])

    G = np.zeros((n_observations, n_model))
    z2 = observation_height ** 2
    grav_const = 6.674e-3  # scaled gravitational constant for numerical range
    for i, (ox, oy) in enumerate(obs_xy):
        dx = source_xy[:, 0] - ox
        dy = source_xy[:, 1] - oy
        r2 = dx ** 2 + dy ** 2 + z2
        G[i, :] = grav_const * observation_height / np.power(r2, 1.5)

    return G


def laplacian_regularizer(grid_shape: tuple[int, int]) -> np.ndarray:
    """Build a 2D discrete Laplacian smoothing regularization matrix."""
    n_rows, n_cols = grid_shape
    n = n_rows * n_cols
    L = np.zeros((n, n))

    def idx(r, c):
        return r * n_cols + c

    for r in range(n_rows):
        for c in range(n_cols):
            i = idx(r, c)
            neighbours = 0
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < n_rows and 0 <= nc < n_cols:
                    L[i, idx(nr, nc)] = -1.0
                    neighbours += 1
            L[i, i] = neighbours
    return L


# ---------------------------------------------------------------------------
# Solvers (vendored from inversion/solvers.py, trimmed to service needs)
# ---------------------------------------------------------------------------
class TikhonovSolver:
    """Linear Tikhonov regularization: min ||Gm - d||^2 + lambda^2 ||Lm||^2."""

    def __init__(self, G: np.ndarray, L: Optional[np.ndarray] = None):
        self.G = G
        self.n_data, self.n_model = G.shape
        self.L = np.eye(self.n_model) if L is None else L

    def solve(self, data: np.ndarray, lambda_reg: float) -> Dict:
        GTG = self.G.T @ self.G
        LTL = self.L.T @ self.L
        GTd = self.G.T @ data
        A = GTG + lambda_reg ** 2 * LTL
        model = np.linalg.solve(A, GTd)
        predicted = self.G @ model
        residual = float(np.linalg.norm(data - predicted))
        return {
            "model": model,
            "predicted_data": predicted,
            "residual": residual,
            "lambda": lambda_reg,
        }

    def l_curve(self, data: np.ndarray, lambdas: np.ndarray):
        residuals = np.zeros_like(lambdas, dtype=float)
        model_norms = np.zeros_like(lambdas, dtype=float)
        for i, lam in enumerate(lambdas):
            res = self.solve(data, lam)
            residuals[i] = res["residual"]
            model_norms[i] = float(np.linalg.norm(self.L @ res["model"]))
        return residuals, model_norms

    def select_lambda_lcurve(self, data: np.ndarray,
                             lambdas: Optional[np.ndarray] = None) -> float:
        """Select regularization parameter using maximum-curvature L-curve."""
        if lambdas is None:
            lambdas = np.logspace(-4, 2, 25)
        residuals, model_norms = self.l_curve(data, lambdas)
        # Work in log-log space; find point of maximum curvature.
        x = np.log10(residuals + 1e-30)
        y = np.log10(model_norms + 1e-30)
        dx = np.gradient(x)
        dy = np.gradient(y)
        d2x = np.gradient(dx)
        d2y = np.gradient(dy)
        curvature = np.abs(dx * d2y - dy * d2x) / np.power(dx ** 2 + dy ** 2, 1.5) + 1e-30
        return float(lambdas[int(np.argmax(curvature))])


class GaussNewtonSolver:
    """Iterative Gauss-Newton solver for (mildly) nonlinear problems.

    For a linear forward operator the iteration converges in one step but the
    iterative structure is retained for progress reporting and to support
    nonlinear forward functions.
    """

    def __init__(self, forward: Callable, jacobian: Callable,
                 L: Optional[np.ndarray] = None):
        self.forward = forward
        self.jacobian = jacobian
        self.L = L

    def solve(self, data: np.ndarray, m_init: np.ndarray, lambda_reg: float,
              max_iter: int = 20, tol: float = 1e-6,
              progress_cb: Optional[Callable[[int, int, float], None]] = None) -> Dict:
        m = m_init.copy()
        if self.L is None:
            self.L = np.eye(len(m))
        history = {"residual": []}
        iteration = 0
        for iteration in range(max_iter):
            d_pred = self.forward(m)
            residual = data - d_pred
            J = self.jacobian(m)
            LTL = self.L.T @ self.L
            A = J.T @ J + lambda_reg ** 2 * LTL
            b = J.T @ residual - lambda_reg ** 2 * LTL @ m
            delta = np.linalg.solve(A, b)
            m = m + delta
            res_norm = float(np.linalg.norm(data - self.forward(m)))
            history["residual"].append(res_norm)
            if progress_cb:
                progress_cb(iteration + 1, max_iter, res_norm)
            if iteration > 0 and abs(history["residual"][-2] - res_norm) < tol:
                break
        return {
            "model": m,
            "predicted_data": self.forward(m),
            "residual": history["residual"][-1] if history["residual"] else 0.0,
            "iterations": iteration + 1,
            "history": history,
            "converged": iteration < max_iter - 1,
        }


class BayesianMAPSolver:
    """Gaussian Bayesian MAP estimate with posterior uncertainty."""

    def __init__(self, G: np.ndarray):
        self.G = G

    def solve(self, data: np.ndarray, m_prior: np.ndarray,
              C_m: np.ndarray, C_d: np.ndarray) -> Dict:
        C_m_inv = np.linalg.inv(C_m)
        C_d_inv = np.linalg.inv(C_d)
        H = C_m_inv + self.G.T @ C_d_inv @ self.G
        rhs = self.G.T @ C_d_inv @ data + C_m_inv @ m_prior
        m_map = np.linalg.solve(H, rhs)
        C_post = np.linalg.inv(H)
        uncertainties = np.sqrt(np.clip(np.diag(C_post), 0, None))
        return {
            "model": m_map,
            "uncertainties": uncertainties,
            "predicted_data": self.G @ m_map,
            "residual": float(np.linalg.norm(data - self.G @ m_map)),
        }


# ---------------------------------------------------------------------------
# Job orchestration
# ---------------------------------------------------------------------------
@dataclass
class InversionJob:
    job_id: str
    inversion_type: str
    status: str = "queued"
    progress: float = 0.0
    current_iteration: int = 0
    total_iterations: int = 0
    residual: float = 0.0
    message: str = "queued"
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    convergence_achieved: bool = False
    model: Optional[np.ndarray] = None
    uncertainties: Optional[np.ndarray] = None
    grid_shape: tuple[int, int] = (0, 0)
    config: Dict = field(default_factory=dict)
    error: Optional[str] = None
    # Real observed gravity data (gridded mGal). When set, the inversion runs
    # on these observations instead of the synthetic forward problem.
    observed_data: Optional[np.ndarray] = None
    # Per-cell measurement counts from the fetcher; cells with zero
    # counts are unobserved and excluded from the data misfit.
    cell_counts: Optional[np.ndarray] = None
    data_source: str = "synthetic"


class InversionEngine:
    """Runs gravity inversions asynchronously with progress tracking.

    Supported ``inversion_type`` values:
      - ``tikhonov`` / ``least_squares`` / ``spherical_harmonics`` -> Tikhonov
      - ``gauss_newton`` -> iterative Gauss-Newton
      - ``bayesian`` -> Bayesian MAP with uncertainty
    """

    def __init__(self):
        self.jobs: Dict[str, InversionJob] = {}
        self._lock = threading.Lock()

    # -- public API --------------------------------------------------------
    def start(self, inversion_type: str, config: Dict[str, str],
              observed_data: Optional[np.ndarray] = None,
              grid_shape: Optional[tuple[int, int]] = None,
              cell_counts: Optional[np.ndarray] = None) -> InversionJob:
        job_id = f"inv_{datetime.utcnow().timestamp()}"
        job = InversionJob(
            job_id=job_id,
            inversion_type=inversion_type or "tikhonov",
            config=dict(config or {}),
        )
        if observed_data is not None:
            job.observed_data = np.asarray(observed_data, dtype=float)
            job.cell_counts = (np.asarray(cell_counts, dtype=float)
                               if cell_counts is not None else None)
            job.data_source = "data_service"
            if grid_shape is not None:
                job.config.setdefault("grid_rows", str(grid_shape[0]))
                job.config.setdefault("grid_cols", str(grid_shape[1]))
        with self._lock:
            self.jobs[job_id] = job

        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        logger.info("Started inversion job %s (%s)", job_id, job.inversion_type)
        return job

    def get(self, job_id: str) -> Optional[InversionJob]:
        with self._lock:
            return self.jobs.get(job_id)

    def list_jobs(self) -> List[InversionJob]:
        with self._lock:
            return list(self.jobs.values())

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self.jobs.get(job_id)
            if job and job.status in ("queued", "running"):
                job.status = "cancelled"
                job.message = "Cancelled by user"
                return True
        return False

    # -- execution ---------------------------------------------------------
    def _run(self, job: InversionJob) -> None:
        try:
            job.status = "running"
            job.message = "Building forward model"

            cfg = job.config
            n_rows = int(cfg.get("grid_rows", 12))
            n_cols = int(cfg.get("grid_cols", 12))
            n_obs = int(cfg.get("n_observations", n_rows * n_cols))
            noise = float(cfg.get("noise_level", 0.02))
            max_iter = int(cfg.get("max_iterations", 50))
            job.grid_shape = (n_rows, n_cols)
            job.total_iterations = max_iter

            rng = np.random.default_rng(int(cfg.get("seed", 7)))
            L = laplacian_regularizer((n_rows, n_cols))

            if job.observed_data is not None:
                # Real data path: measurements were binned onto grid
                # cells by the fetcher. The observation operator is the
                # SELECTION of populated cells (no fabricated random
                # kernel), and Tikhonov+Laplacian completes the map
                # smoothly across unobserved cells:
                #   min ||S m - d||^2 + lambda^2 ||L m||^2
                job.message = "Inverting observed gravity data"
                full = job.observed_data.ravel()
                counts = (job.cell_counts.ravel()
                          if getattr(job, "cell_counts", None) is not None
                          else np.ones_like(full))
                mask = counts > 0
                if not np.any(mask):
                    raise ValueError("no populated grid cells in observations")
                data = full[mask]
                n_obs = int(mask.sum())
                G = np.zeros((n_obs, n_rows * n_cols))
                G[np.arange(n_obs), np.flatnonzero(mask)] = 1.0
                true_model = None
            else:
                # Synthetic path: known "true" model for validation.
                G = build_point_mass_operator((n_rows, n_cols), n_obs, rng=rng)
                true_model = self._synthetic_anomaly((n_rows, n_cols))
                clean = G @ true_model
                data = clean + noise * np.linalg.norm(clean) / np.sqrt(len(clean)) * rng.standard_normal(len(clean))

            # Check if multiscale solving is requested
            use_multiscale = cfg.get("use_multiscale", "false").lower() == "true"
            multiscale_levels = int(cfg.get("multiscale_levels", 3))

            if use_multiscale and _HAS_MULTISCALE and n_rows >= 16 and n_cols >= 16:
                # Use hierarchical multiscale solver
                job.message = "Running multi-scale inversion"
                result = self._run_multiscale(
                    job, data, (n_rows, n_cols),
                    multiscale_levels, rng, job.inversion_type
                )
            else:
                # Standard single-scale solvers
                itype = job.inversion_type.lower()
                if itype in ("bayesian", "map"):
                    result = self._run_bayesian(job, G, data, true_model)
                elif itype in ("gauss_newton", "gauss-newton", "gn"):
                    result = self._run_gauss_newton(job, G, L, data, max_iter)
                else:  # tikhonov / least_squares / spherical_harmonics / default
                    result = self._run_tikhonov(job, G, L, data)

            if job.status == "cancelled":
                return

            job.model = result["model"]
            job.uncertainties = result.get("uncertainties")
            job.residual = result["residual"]
            job.progress = 1.0
            job.convergence_achieved = result.get("residual", 1.0) < float(cfg.get("convergence_threshold", 1e-2))
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            if true_model is not None:
                # Synthetic: report model recovery quality.
                denom = np.linalg.norm(true_model) or 1.0
                model_error = float(np.linalg.norm(job.model - true_model) / denom)
                job.message = (
                    f"Inversion complete ({job.data_source}): "
                    f"residual={job.residual:.4e}, model_error={model_error:.3f}"
                )
            else:
                job.message = (
                    f"Inversion complete ({job.data_source}): "
                    f"residual={job.residual:.4e}, cells={data.size}"
                )
            logger.info("Inversion job %s completed: %s", job.job_id, job.message)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the job
            logger.exception("Inversion job %s failed", job.job_id)
            job.status = "failed"
            job.error = str(exc)
            job.message = f"Inversion failed: {exc}"
            job.completed_at = datetime.utcnow()

    def _run_tikhonov(self, job, G, L, data) -> Dict:
        solver = TikhonovSolver(G, L)
        job.message = "Selecting regularization parameter (L-curve)"
        job.progress = 0.2
        lam = solver.select_lambda_lcurve(data)
        job.config["lambda"] = f"{lam:.4e}"
        job.message = f"Solving Tikhonov system (lambda={lam:.3e})"
        job.progress = 0.6
        result = solver.solve(data, lam)
        job.current_iteration = 1
        job.residual = result["residual"]
        job.progress = 0.95
        return result

    def _run_gauss_newton(self, job, G, L, data, max_iter) -> Dict:
        forward = lambda m: G @ m  # noqa: E731 - linear forward model
        jacobian = lambda m: G  # noqa: E731 - constant Jacobian (linear)
        solver = GaussNewtonSolver(forward, jacobian, L)
        m_init = np.zeros(G.shape[1])

        def progress_cb(it, total, res):
            if job.status == "cancelled":
                raise RuntimeError("cancelled")
            job.current_iteration = it
            job.total_iterations = total
            job.residual = res
            job.progress = min(0.95, it / max(total, 1))

        lam = float(job.config.get("lambda", 0.01))
        try:
            return solver.solve(data, m_init, lambda_reg=lam,
                                max_iter=max_iter, progress_cb=progress_cb)
        except RuntimeError:
            return {"model": m_init, "residual": float(np.linalg.norm(data)), "iterations": 0}

    def _run_bayesian(self, job, G, data, true_model) -> Dict:
        job.message = "Bayesian MAP estimation"
        job.progress = 0.4
        n_model = G.shape[1]
        C_m = np.eye(n_model) * float(job.config.get("prior_variance", 1.0))
        C_d = np.eye(G.shape[0]) * float(job.config.get("data_variance", 1e-3))
        m_prior = np.zeros(n_model)
        solver = BayesianMAPSolver(G)
        result = solver.solve(data, m_prior, C_m, C_d)
        job.current_iteration = 1
        job.residual = result["residual"]
        job.progress = 0.95
        return result

    def _run_multiscale(
        self,
        job: InversionJob,
        data: np.ndarray,
        grid_shape: tuple[int, int],
        levels: int,
        rng: np.random.Generator,
        method: str
    ) -> Dict:
        """Run multi-scale hierarchical inversion."""
        job.message = f"Multi-scale inversion ({levels} levels)"
        job.progress = 0.1

        # Operator builder for different grid sizes
        def operator_builder(shape):
            n_obs = data.size
            return build_point_mass_operator(shape, n_obs, rng=rng)

        # Create multiscale solver
        ms_solver = MultiscaleInversionEngine(
            levels=levels,
            wavelet="db4",
            refinement_threshold=0.1,
            max_active_fraction=0.3
        )

        # Determine base method
        base_method = "tikhonov"
        if method.lower() in ("gauss_newton", "gauss-newton", "gn"):
            base_method = "gauss_newton"

        # Regularization parameter
        lambda_reg = float(job.config.get("lambda", 0.1))

        # Run multi-scale solve
        logger.info(
            f"Starting {levels}-level multiscale inversion on {grid_shape} grid"
        )

        try:
            ms_result = ms_solver.solve_multiscale(
                observations=data,
                operator_builder=operator_builder,
                grid_shape=grid_shape,
                method=base_method,
                lambda_reg=lambda_reg,
                tolerance=1e-3
            )

            job.current_iteration = ms_result.iterations
            job.total_iterations = ms_result.iterations
            job.residual = ms_result.misfit
            job.progress = 0.95

            # Store multiscale metrics
            job.config["multiscale_speedup"] = f"{ms_result.speedup_factor:.1f}x"
            job.config["refinement_levels"] = str(ms_result.refinement_levels)

            logger.info(
                f"Multiscale solve complete: {ms_result.speedup_factor:.1f}x speedup, "
                f"misfit={ms_result.misfit:.4f}"
            )

            return {
                "model": ms_result.model,
                "residual": ms_result.misfit,
                "predicted_data": data - ms_result.residuals,
                "lambda": lambda_reg,
                "iterations": ms_result.iterations
            }

        except Exception as e:
            logger.error(f"Multiscale solve failed: {e}, falling back to single-scale")
            # Fallback to single-scale
            G = operator_builder(grid_shape)
            L = laplacian_regularizer(grid_shape)
            return self._run_tikhonov(job, G, L, data)

    @staticmethod
    def _synthetic_anomaly(grid_shape: tuple[int, int]) -> np.ndarray:
        n_rows, n_cols = grid_shape
        yy, xx = np.mgrid[0:n_rows, 0:n_cols]
        cy, cx = n_rows / 2.0, n_cols / 2.0
        sigma = max(n_rows, n_cols) / 6.0
        blob = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
        return blob.ravel()
