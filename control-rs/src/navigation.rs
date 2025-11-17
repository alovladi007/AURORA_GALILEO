/*!
Navigation Filters: EKF and UKF
================================

Extended Kalman Filter (EKF) and Unscented Kalman Filter (UKF) for
nonlinear state estimation in spacecraft navigation.

EKF: Linearizes dynamics/measurements using Jacobians
UKF: Uses sigma points for better handling of nonlinearity
*/

use nalgebra::{DMatrix, DVector};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use numpy::{PyArray1, PyArray2, PyReadonlyArray2, PyReadonlyArray1};
use std::f64::consts::PI;

/// Error types for navigation filters
#[derive(Debug, thiserror::Error)]
pub enum FilterError {
    #[error("Dimension mismatch: {0}")]
    DimensionError(String),

    #[error("Numerical error: {0}")]
    NumericalError(String),
}

impl From<FilterError> for PyErr {
    fn from(err: FilterError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

/// Extended Kalman Filter (EKF)
///
/// For systems:
///     x_{k+1} = f(x_k, u_k) + w_k,  w_k ~ N(0, Q)
///     y_k = h(x_k) + v_k,           v_k ~ N(0, R)
#[pyclass]
pub struct EKF {
    /// State dimension
    n: usize,

    /// Measurement dimension
    m: usize,

    /// State estimate
    x: DVector<f64>,

    /// Covariance matrix
    p: DMatrix<f64>,

    /// Process noise covariance
    q: DMatrix<f64>,

    /// Measurement noise covariance
    r: DMatrix<f64>,
}

#[pymethods]
impl EKF {
    /// Create new EKF
    ///
    /// # Arguments
    /// * `x0` - Initial state estimate (n,)
    /// * `p0` - Initial covariance (n × n)
    /// * `q` - Process noise covariance (n × n)
    /// * `r` - Measurement noise covariance (m × m)
    #[new]
    pub fn new(
        x0: PyReadonlyArray1<f64>,
        p0: PyReadonlyArray2<f64>,
        q: PyReadonlyArray2<f64>,
        r: PyReadonlyArray2<f64>,
    ) -> PyResult<Self> {
        let x0_arr = x0.as_array();
        let p0_arr = p0.as_array();
        let q_arr = q.as_array();
        let r_arr = r.as_array();

        let n = x0_arr.len();
        let m = r_arr.nrows();

        let x = DVector::from_row_slice(x0_arr.as_slice().unwrap());
        let p = DMatrix::from_row_slice(n, n, p0_arr.as_slice().unwrap());
        let q_mat = DMatrix::from_row_slice(n, n, q_arr.as_slice().unwrap());
        let r_mat = DMatrix::from_row_slice(m, m, r_arr.as_slice().unwrap());

        Ok(Self { n, m, x, p, q: q_mat, r: r_mat })
    }

    /// Predict step
    ///
    /// # Arguments
    /// * `f` - State transition Jacobian F (n × n)
    /// * `x_pred` - Predicted state from nonlinear dynamics (n,)
    pub fn predict(
        &mut self,
        f: PyReadonlyArray2<f64>,
        x_pred: PyReadonlyArray1<f64>,
    ) -> PyResult<()> {
        let f_arr = f.as_array();
        let x_pred_arr = x_pred.as_array();

        let f_mat = DMatrix::from_row_slice(self.n, self.n, f_arr.as_slice().unwrap());
        let x_new = DVector::from_row_slice(x_pred_arr.as_slice().unwrap());

        // x = x_pred (from nonlinear propagation)
        self.x = x_new;

        // P = F P F^T + Q
        self.p = &f_mat * &self.p * f_mat.transpose() + &self.q;

        Ok(())
    }

    /// Update step
    ///
    /// # Arguments
    /// * `h` - Measurement Jacobian H (m × n)
    /// * `y` - Measurement vector (m,)
    /// * `y_pred` - Predicted measurement from h(x) (m,)
    pub fn update(
        &mut self,
        h: PyReadonlyArray2<f64>,
        y: PyReadonlyArray1<f64>,
        y_pred: PyReadonlyArray1<f64>,
    ) -> PyResult<()> {
        let h_arr = h.as_array();
        let y_arr = y.as_array();
        let y_pred_arr = y_pred.as_array();

        let h_mat = DMatrix::from_row_slice(self.m, self.n, h_arr.as_slice().unwrap());
        let y_vec = DVector::from_row_slice(y_arr.as_slice().unwrap());
        let y_pred_vec = DVector::from_row_slice(y_pred_arr.as_slice().unwrap());

        // Innovation: y - h(x)
        let innov = y_vec - y_pred_vec;

        // Innovation covariance: S = H P H^T + R
        let s = &h_mat * &self.p * h_mat.transpose() + &self.r;

        // Kalman gain: K = P H^T S^{-1}
        let s_inv = s.try_inverse().ok_or_else(|| {
            FilterError::NumericalError("Innovation covariance not invertible".to_string())
        })?;

        let k = &self.p * h_mat.transpose() * s_inv;

        // State update: x = x + K * innov
        self.x += &k * innov;

        // Covariance update: P = (I - K H) P
        let i = DMatrix::identity(self.n, self.n);
        let kh = &k * h_mat;
        self.p = (i - kh) * &self.p;

        Ok(())
    }

    /// Get current state estimate
    #[getter]
    pub fn state<'py>(&self, py: Python<'py>) -> &'py PyArray1<f64> {
        PyArray1::from_vec(py, self.x.as_slice().to_vec())
    }

    /// Get current covariance
    #[getter]
    pub fn covariance<'py>(&self, py: Python<'py>) -> &'py PyArray2<f64> {
        let data = self.p.as_slice().to_vec();
        PyArray2::from_vec2(py, &data.chunks(self.n)
            .map(|chunk| chunk.to_vec())
            .collect::<Vec<_>>())
            .unwrap()
    }

    /// Get state dimension
    #[getter]
    pub fn state_dim(&self) -> usize {
        self.n
    }

    /// Get measurement dimension
    #[getter]
    pub fn meas_dim(&self) -> usize {
        self.m
    }
}

/// Unscented Kalman Filter (UKF)
///
/// Uses sigma points for nonlinear transformations.
#[pyclass]
pub struct UKF {
    /// State dimension
    n: usize,

    /// Measurement dimension
    m: usize,

    /// State estimate
    x: DVector<f64>,

    /// Covariance matrix
    p: DMatrix<f64>,

    /// Process noise covariance
    q: DMatrix<f64>,

    /// Measurement noise covariance
    r: DMatrix<f64>,

    /// UKF parameters
    alpha: f64,
    beta: f64,
    kappa: f64,

    /// Computed weights
    wm: Vec<f64>,  // Mean weights
    wc: Vec<f64>,  // Covariance weights
}

impl UKF {
    /// Compute UKF weights
    fn compute_weights(n: usize, alpha: f64, beta: f64, kappa: f64) -> (Vec<f64>, Vec<f64>) {
        let lambda = alpha * alpha * (n as f64 + kappa) - n as f64;
        let num_sigma = 2 * n + 1;

        let mut wm = vec![0.0; num_sigma];
        let mut wc = vec![0.0; num_sigma];

        // Weight for mean sigma point
        wm[0] = lambda / (n as f64 + lambda);
        wc[0] = lambda / (n as f64 + lambda) + (1.0 - alpha * alpha + beta);

        // Weights for other sigma points
        let w = 0.5 / (n as f64 + lambda);
        for i in 1..num_sigma {
            wm[i] = w;
            wc[i] = w;
        }

        (wm, wc)
    }

    /// Generate sigma points
    fn generate_sigma_points(&self) -> Result<Vec<DVector<f64>>, FilterError> {
        let n = self.n;
        let alpha = self.alpha;
        let kappa = self.kappa;
        let lambda = alpha * alpha * (n as f64 + kappa) - n as f64;

        // Compute sqrt((n + lambda) * P) using Cholesky
        let scale = n as f64 + lambda;
        let scaled_p = &self.p * scale;

        let chol = scaled_p.cholesky().ok_or_else(|| {
            FilterError::NumericalError("Covariance not positive definite".to_string())
        })?;

        let sqrt_p = chol.l();

        let mut sigma_points = Vec::new();

        // Mean sigma point
        sigma_points.push(self.x.clone());

        // Positive direction
        for i in 0..n {
            let col = sqrt_p.column(i);
            sigma_points.push(&self.x + col);
        }

        // Negative direction
        for i in 0..n {
            let col = sqrt_p.column(i);
            sigma_points.push(&self.x - col);
        }

        Ok(sigma_points)
    }
}

#[pymethods]
impl UKF {
    /// Create new UKF
    ///
    /// # Arguments
    /// * `x0` - Initial state estimate (n,)
    /// * `p0` - Initial covariance (n × n)
    /// * `q` - Process noise covariance (n × n)
    /// * `r` - Measurement noise covariance (m × m)
    /// * `alpha` - Spread of sigma points (default: 1e-3)
    /// * `beta` - Prior knowledge of distribution (default: 2.0 for Gaussian)
    /// * `kappa` - Secondary scaling parameter (default: 0.0)
    #[new]
    #[pyo3(signature = (x0, p0, q, r, alpha=1e-3, beta=2.0, kappa=0.0))]
    pub fn new(
        x0: PyReadonlyArray1<f64>,
        p0: PyReadonlyArray2<f64>,
        q: PyReadonlyArray2<f64>,
        r: PyReadonlyArray2<f64>,
        alpha: f64,
        beta: f64,
        kappa: f64,
    ) -> PyResult<Self> {
        let x0_arr = x0.as_array();
        let p0_arr = p0.as_array();
        let q_arr = q.as_array();
        let r_arr = r.as_array();

        let n = x0_arr.len();
        let m = r_arr.nrows();

        let x = DVector::from_row_slice(x0_arr.as_slice().unwrap());
        let p = DMatrix::from_row_slice(n, n, p0_arr.as_slice().unwrap());
        let q_mat = DMatrix::from_row_slice(n, n, q_arr.as_slice().unwrap());
        let r_mat = DMatrix::from_row_slice(m, m, r_arr.as_slice().unwrap());

        let (wm, wc) = Self::compute_weights(n, alpha, beta, kappa);

        Ok(Self {
            n,
            m,
            x,
            p,
            q: q_mat,
            r: r_mat,
            alpha,
            beta,
            kappa,
            wm,
            wc,
        })
    }

    /// Predict step (requires external nonlinear propagation of sigma points)
    ///
    /// # Arguments
    /// * `sigma_points_pred` - Propagated sigma points (2n+1 × n)
    pub fn predict(&mut self, sigma_points_pred: PyReadonlyArray2<f64>) -> PyResult<()> {
        let sp_arr = sigma_points_pred.as_array();

        // Convert to vectors
        let mut sigma_vecs = Vec::new();
        for i in 0..(2 * self.n + 1) {
            let row = sp_arr.row(i);
            sigma_vecs.push(DVector::from_row_slice(row.as_slice().unwrap()));
        }

        // Compute predicted mean
        let mut x_pred = DVector::zeros(self.n);
        for (i, sp) in sigma_vecs.iter().enumerate() {
            x_pred += sp * self.wm[i];
        }

        // Compute predicted covariance
        let mut p_pred = DMatrix::zeros(self.n, self.n);
        for (i, sp) in sigma_vecs.iter().enumerate() {
            let diff = sp - &x_pred;
            p_pred += (diff.clone() * diff.transpose()) * self.wc[i];
        }

        p_pred += &self.q;

        self.x = x_pred;
        self.p = p_pred;

        Ok(())
    }

    /// Update step
    ///
    /// # Arguments
    /// * `sigma_points_meas` - Measurement sigma points (2n+1 × m)
    /// * `y` - Actual measurement (m,)
    pub fn update(
        &mut self,
        sigma_points_meas: PyReadonlyArray2<f64>,
        y: PyReadonlyArray1<f64>,
    ) -> PyResult<()> {
        let spm_arr = sigma_points_meas.as_array();
        let y_arr = y.as_array();

        // Convert to vectors
        let mut meas_vecs = Vec::new();
        for i in 0..(2 * self.n + 1) {
            let row = spm_arr.row(i);
            meas_vecs.push(DVector::from_row_slice(row.as_slice().unwrap()));
        }

        let y_vec = DVector::from_row_slice(y_arr.as_slice().unwrap());

        // Predicted measurement mean
        let mut y_pred = DVector::zeros(self.m);
        for (i, ym) in meas_vecs.iter().enumerate() {
            y_pred += ym * self.wm[i];
        }

        // Innovation covariance
        let mut s = DMatrix::zeros(self.m, self.m);
        for (i, ym) in meas_vecs.iter().enumerate() {
            let diff = ym - &y_pred;
            s += (diff.clone() * diff.transpose()) * self.wc[i];
        }
        s += &self.r;

        // Cross-covariance
        let sigma_points = self.generate_sigma_points()?;
        let mut pxy = DMatrix::zeros(self.n, self.m);
        for i in 0..(2 * self.n + 1) {
            let x_diff = &sigma_points[i] - &self.x;
            let y_diff = &meas_vecs[i] - &y_pred;
            pxy += (x_diff * y_diff.transpose()) * self.wc[i];
        }

        // Kalman gain
        let s_inv = s.clone().try_inverse().ok_or_else(|| {
            FilterError::NumericalError("Innovation covariance not invertible".to_string())
        })?;

        let k = pxy * s_inv;

        // State update
        let innov = y_vec - y_pred;
        self.x += &k * innov;

        // Covariance update
        self.p = &self.p - &k * s * k.transpose();

        Ok(())
    }

    /// Get current state estimate
    #[getter]
    pub fn state<'py>(&self, py: Python<'py>) -> &'py PyArray1<f64> {
        PyArray1::from_vec(py, self.x.as_slice().to_vec())
    }

    /// Get current covariance
    #[getter]
    pub fn covariance<'py>(&self, py: Python<'py>) -> &'py PyArray2<f64> {
        let data = self.p.as_slice().to_vec();
        PyArray2::from_vec2(py, &data.chunks(self.n)
            .map(|chunk| chunk.to_vec())
            .collect::<Vec<_>>())
            .unwrap()
    }

    /// Generate and return sigma points for external propagation
    pub fn get_sigma_points<'py>(&self, py: Python<'py>) -> PyResult<&'py PyArray2<f64>> {
        let sigma_points = self.generate_sigma_points()
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let mut data = Vec::new();
        for sp in &sigma_points {
            data.extend_from_slice(sp.as_slice());
        }

        PyArray2::from_vec2(py, &data.chunks(self.n)
            .map(|chunk| chunk.to_vec())
            .collect::<Vec<_>>())
            .map_err(|e| PyValueError::new_err(format!("Failed to create sigma points array: {:?}", e)))
    }

    /// Get state dimension
    #[getter]
    pub fn state_dim(&self) -> usize {
        self.n
    }

    /// Get measurement dimension
    #[getter]
    pub fn meas_dim(&self) -> usize {
        self.m
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ukf_weights() {
        let n = 3;
        let alpha = 1e-3;
        let beta = 2.0;
        let kappa = 0.0;

        let (wm, wc) = UKF::compute_weights(n, alpha, beta, kappa);

        // Should have 2n+1 weights
        assert_eq!(wm.len(), 2 * n + 1);
        assert_eq!(wc.len(), 2 * n + 1);

        // Weights should sum to 1
        let sum_wm: f64 = wm.iter().sum();
        assert!((sum_wm - 1.0).abs() < 1e-10);
    }
}
