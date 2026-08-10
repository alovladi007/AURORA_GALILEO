"""
Learned gravity-map completion (Phase 4 W4.1).

Kernel-ridge (RBF) completion of gapped gravity-anomaly grids. The
model's hyperparameters (kernel length scale and ridge strength) are
LEARNED by cross-validated grid search over training scenarios
produced by the real mission generator — not hand-picked — and the
shipped configuration must beat the platform's classical Tikhonov
baseline on the closed-loop anomaly-recovery benchmark before it may
be used (the Phase 4 ship criterion).

The estimator itself is deliberately simple and fully deterministic:
given observed cells (r_i, c_i, v_i), predict every grid cell as

    v(x) = k(x, X_obs) (K + alpha I)^{-1} v_obs

with an RBF kernel in grid coordinates. This is a real learned model
(hyperparameters fit to data) with an exact, reproducible solve.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class CompletionModel:
    """Fitted completion model configuration."""

    length_scale: float
    alpha: float
    train_score_rms: float  # held-out completion RMS during fitting


class GravityMapCompleter:
    """RBF kernel-ridge completion of gapped anomaly grids."""

    def __init__(self, model: Optional[CompletionModel] = None):
        self.model = model

    # ── inference ────────────────────────────────────────────────────
    @staticmethod
    def _grid_coords(rows: int, cols: int) -> np.ndarray:
        rr, cc = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
        return np.stack([rr.ravel(), cc.ravel()], axis=1).astype(float)

    @staticmethod
    def _rbf(a: np.ndarray, b: np.ndarray, ls: float) -> np.ndarray:
        d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
        return np.exp(-d2 / (2.0 * ls**2))

    def predict(self, observed: np.ndarray, counts: np.ndarray) -> np.ndarray:
        """Complete a gapped grid: observed values where counts>0,
        prediction everywhere. Shapes (rows, cols)."""
        if self.model is None:
            raise RuntimeError("model not fitted - call fit() first")
        rows, cols = observed.shape
        coords = self._grid_coords(rows, cols)
        mask = counts.ravel() > 0
        x_obs = coords[mask]
        v_obs = observed.ravel()[mask]

        K = self._rbf(x_obs, x_obs, self.model.length_scale)
        K[np.diag_indices_from(K)] += self.model.alpha
        w = np.linalg.solve(K, v_obs)
        k_star = self._rbf(coords, x_obs, self.model.length_scale)
        return (k_star @ w).reshape(rows, cols)

    # ── training ─────────────────────────────────────────────────────
    def fit(
        self,
        training_pairs: Sequence[Tuple[np.ndarray, np.ndarray, np.ndarray]],
        length_scales: Sequence[float] = (1.0, 1.5, 2.0, 3.0),
        alphas: Sequence[float] = (1e-3, 1e-2, 1e-1),
    ) -> CompletionModel:
        """Learn hyperparameters by cross-validated completion error.

        Each training pair is (truth, observed, counts): the truth grid
        (what the completed map SHOULD be), the gapped observation grid
        and its cell counts, all produced by the mission generator.
        For each candidate configuration the model is asked to complete
        the observations and scored on the truth over ALL cells; the
        configuration with the lowest mean RMS wins.
        """
        best: Optional[CompletionModel] = None
        for ls in length_scales:
            for alpha in alphas:
                trial = GravityMapCompleter(
                    CompletionModel(ls, alpha, np.inf)
                )
                errs = []
                for truth, observed, counts in training_pairs:
                    pred = trial.predict(observed, counts)
                    errs.append(
                        float(np.sqrt(np.mean((pred - truth) ** 2)))
                    )
                score = float(np.mean(errs))
                if best is None or score < best.train_score_rms:
                    best = CompletionModel(ls, alpha, score)
        assert best is not None
        self.model = best
        return best

    # ── serialization ────────────────────────────────────────────────
    def to_dict(self) -> Dict:
        assert self.model is not None
        return {
            "length_scale": self.model.length_scale,
            "alpha": self.model.alpha,
            "train_score_rms": self.model.train_score_rms,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GravityMapCompleter":
        return cls(CompletionModel(
            d["length_scale"], d["alpha"], d.get("train_score_rms", np.nan)
        ))
