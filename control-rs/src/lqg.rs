/*!
Linear Quadratic Gaussian (LQG)
================================

Combines LQR control with Kalman filter state estimation.

LQG = LQR (optimal controller) + Kalman filter (optimal estimator)

For systems:
    x_{k+1} = A x_k + B u_k + w_k,  w_k ~ N(0, Q_w)
    y_k = C x_k + v_k,              v_k ~ N(0, R_v)

Separates into:
- Control law: u = -K x_hat
- Estimation: Kalman filter for x_hat
*/

use nalgebra::{DMatrix, DVector};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use numpy::{PyArray1, PyArray2, PyReadonlyArray2, PyReadonlyArray1};
use ndarray::Array2;

use crate::lqr::{solve_care, compute_lqr_gain, LQRError};

/// Error types for LQG
#[derive(Debug, thiserror::Error)]
pub enum LQGError {
    #[error("Dimension mismatch: {0}")]
    DimensionError(String),

    #[error("LQR error: {0}")]
    LQRError(#[from] LQRError),

    #[error("Numerical error: {0}")]
    NumericalError(String),
}

impl From<LQGError> for PyErr {
    fn from(err: LQGError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

/// Solve Dual Algebraic Riccati Equation for Kalman gain
///
/// Solves: A P A^T - P - A P C^T (C P C^T + R)^{-1} C P A^T + Q = 0
///
/// This is the filter DARE, dual to the control CARE.
fn solve_filter_dare(
    a: &Array2<f64>,
    c: &Array2<f64>,
    q_w: &Array2<f64>,
    r_v: &Array2<f64>,
) -> Result<Array2<f64>, LQGError> {
    // Use duality: filter DARE <-> control CARE
    // with substitutions: A -> A^T, B -> C^T, Q -> Q_w, R -> R_v

    let a_t = a.t().to_owned();
    let c_t = c.t().to_owned();

    let p = solve_care(&a_t, &c_t, q_w, r_v)?;

    Ok(p)
}

/// Compute Kalman filter gain
///
/// L = P C^T (C P C^T + R)^{-1}
fn compute_kalman_gain(
    c: &Array2<f64>,
    r_v: &Array2<f64>,
    p: &Array2<f64>,
) -> Result<Array2<f64>, LQGError> {
    use ndarray_linalg::Inverse;

    let cpc_t = c.dot(p).dot(&c.t());
    let s = cpc_t + r_v;

    let s_inv = s.inv().map_err(|_| {
        LQGError::NumericalError("Innovation covariance not invertible".to_string())
    })?;

    let l = p.dot(&c.t()).dot(&s_inv);

    Ok(l)
}

/// LQG Controller with Python bindings
///
/// Combines optimal control (LQR) with optimal estimation (Kalman filter).
#[pyclass]
pub struct LQGController {
    /// System matrices
    a: DMatrix<f64>,
    b: DMatrix<f64>,
    c: DMatrix<f64>,

    /// Control gain K
    k: DMatrix<f64>,

    /// Estimator gain L
    l: DMatrix<f64>,

    /// State estimate
    x_hat: DVector<f64>,

    /// State dimension
    n: usize,

    /// Input dimension
    m: usize,

    /// Output dimension
    p: usize,
}

#[pymethods]
impl LQGController {
    /// Create new LQG controller
    ///
    /// # Arguments
    /// * `a` - State matrix (n × n)
    /// * `b` - Input matrix (n × m)
    /// * `c` - Output matrix (p × n)
    /// * `q_cost` - State cost for LQR (n × n)
    /// * `r_cost` - Input cost for LQR (m × m)
    /// * `q_w` - Process noise covariance (n × n)
    /// * `r_v` - Measurement noise covariance (p × p)
    /// * `x0` - Initial state estimate (n,)
    #[new]
    pub fn new(
        a: PyReadonlyArray2<f64>,
        b: PyReadonlyArray2<f64>,
        c: PyReadonlyArray2<f64>,
        q_cost: PyReadonlyArray2<f64>,
        r_cost: PyReadonlyArray2<f64>,
        q_w: PyReadonlyArray2<f64>,
        r_v: PyReadonlyArray2<f64>,
        x0: PyReadonlyArray1<f64>,
    ) -> PyResult<Self> {
        let a_arr = a.as_array().to_owned();
        let b_arr = b.as_array().to_owned();
        let c_arr = c.as_array().to_owned();
        let q_cost_arr = q_cost.as_array().to_owned();
        let r_cost_arr = r_cost.as_array().to_owned();
        let q_w_arr = q_w.as_array().to_owned();
        let r_v_arr = r_v.as_array().to_owned();
        let x0_arr = x0.as_array();

        let n = a_arr.nrows();
        let m = b_arr.ncols();
        let p = c_arr.nrows();

        // Solve CARE for control gain K
        let p_ctrl = solve_care(&a_arr, &b_arr, &q_cost_arr, &r_cost_arr)
            .map_err(|e| LQGError::from(e))?;

        let k_arr = compute_lqr_gain(&b_arr, &r_cost_arr, &p_ctrl)
            .map_err(|e| LQGError::from(e))?;

        // Solve DARE for estimator gain L
        let p_est = solve_filter_dare(&a_arr, &c_arr, &q_w_arr, &r_v_arr)?;

        let l_arr = compute_kalman_gain(&c_arr, &r_v_arr, &p_est)?;

        // Convert to nalgebra
        let a_mat = DMatrix::from_row_slice(n, n, a_arr.as_slice().unwrap());
        let b_mat = DMatrix::from_row_slice(n, m, b_arr.as_slice().unwrap());
        let c_mat = DMatrix::from_row_slice(p, n, c_arr.as_slice().unwrap());
        let k_mat = DMatrix::from_row_slice(k_arr.nrows(), k_arr.ncols(), k_arr.as_slice().unwrap());
        let l_mat = DMatrix::from_row_slice(l_arr.nrows(), l_arr.ncols(), l_arr.as_slice().unwrap());
        let x_hat_vec = DVector::from_row_slice(x0_arr.as_slice().unwrap());

        Ok(Self {
            a: a_mat,
            b: b_mat,
            c: c_mat,
            k: k_mat,
            l: l_mat,
            x_hat: x_hat_vec,
            n,
            m,
            p,
        })
    }

    /// Compute control and update estimate
    ///
    /// # Arguments
    /// * `y` - Measurement vector (p,)
    ///
    /// # Returns
    /// Control input u (m,)
    ///
    /// # Algorithm
    /// 1. Compute control: u = -K * x_hat
    /// 2. Predict: x_hat_pred = A * x_hat + B * u
    /// 3. Correct: x_hat = x_hat_pred + L * (y - C * x_hat_pred)
    pub fn step<'py>(
        &mut self,
        py: Python<'py>,
        y: PyReadonlyArray1<f64>,
    ) -> PyResult<&'py PyArray1<f64>> {
        let y_arr = y.as_array();

        if y_arr.len() != self.p {
            return Err(LQGError::DimensionError(
                format!("Measurement must have length {}, got {}", self.p, y_arr.len())
            ).into());
        }

        let y_vec = DVector::from_row_slice(y_arr.as_slice().unwrap());

        // Control law: u = -K * x_hat
        let u = -&self.k * &self.x_hat;

        // State prediction: x_hat_pred = A * x_hat + B * u
        let x_hat_pred = &self.a * &self.x_hat + &self.b * &u;

        // Measurement prediction: y_pred = C * x_hat_pred
        let y_pred = &self.c * &x_hat_pred;

        // Innovation: y - y_pred
        let innov = y_vec - y_pred;

        // State correction: x_hat = x_hat_pred + L * innov
        self.x_hat = x_hat_pred + &self.l * innov;

        // Return control
        Ok(PyArray1::from_vec(py, u.as_slice().to_vec()))
    }

    /// Get current state estimate
    #[getter]
    pub fn state_estimate<'py>(&self, py: Python<'py>) -> &'py PyArray1<f64> {
        PyArray1::from_vec(py, self.x_hat.as_slice().to_vec())
    }

    /// Get control gain K
    #[getter]
    pub fn control_gain<'py>(&self, py: Python<'py>) -> &'py PyArray2<f64> {
        let data = self.k.as_slice().to_vec();
        PyArray2::from_vec2(py, &data.chunks(self.n)
            .map(|chunk| chunk.to_vec())
            .collect::<Vec<_>>())
            .unwrap()
    }

    /// Get estimator gain L
    #[getter]
    pub fn estimator_gain<'py>(&self, py: Python<'py>) -> &'py PyArray2<f64> {
        let data = self.l.as_slice().to_vec();
        PyArray2::from_vec2(py, &data.chunks(self.p)
            .map(|chunk| chunk.to_vec())
            .collect::<Vec<_>>())
            .unwrap()
    }

    /// Reset state estimate
    pub fn reset(&mut self, x0: PyReadonlyArray1<f64>) -> PyResult<()> {
        let x0_arr = x0.as_array();

        if x0_arr.len() != self.n {
            return Err(LQGError::DimensionError(
                format!("State must have length {}, got {}", self.n, x0_arr.len())
            ).into());
        }

        self.x_hat = DVector::from_row_slice(x0_arr.as_slice().unwrap());
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;

    #[test]
    fn test_filter_dare_simple() {
        // Simple 1D system
        let a = array![[0.9]];
        let c = array![[1.0]];
        let q_w = array![[0.1]];
        let r_v = array![[0.1]];

        let p = solve_filter_dare(&a, &c, &q_w, &r_v).unwrap();

        // P should be positive
        assert!(p[[0, 0]] > 0.0);
    }

    #[test]
    fn test_kalman_gain() {
        let c = array![[1.0, 0.0]];
        let r_v = array![[1.0]];
        let p = array![[2.0, 0.0], [0.0, 2.0]];

        let l = compute_kalman_gain(&c, &r_v, &p).unwrap();

        // L should have correct dimensions
        assert_eq!(l.shape(), &[2, 1]);
    }
}
