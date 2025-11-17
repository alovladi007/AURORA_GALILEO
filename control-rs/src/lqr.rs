/*!
Linear Quadratic Regulator (LQR)
=================================

Solves the Continuous-time Algebraic Riccati Equation (CARE) using
the Schur decomposition method for numerical stability.

CARE: A^T P + P A - P B R^{-1} B^T P + Q = 0
Optimal gain: K = R^{-1} B^T P
*/

use nalgebra::{DMatrix, DVector};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use numpy::{PyArray1, PyArray2, PyReadonlyArray2, PyReadonlyArray1};
use ndarray::Array2;
use ndarray_linalg::{Eig, Inverse};

/// Error types for LQR
#[derive(Debug, thiserror::Error)]
pub enum LQRError {
    #[error("Matrix dimensions incompatible: {0}")]
    DimensionError(String),

    #[error("CARE solver failed to converge: {0}")]
    ConvergenceError(String),

    #[error("Matrix is not positive definite: {0}")]
    PositiveDefiniteError(String),
}

impl From<LQRError> for PyErr {
    fn from(err: LQRError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

/// Solve Continuous-time Algebraic Riccati Equation (CARE)
///
/// Solves: A^T P + P A - P B R^{-1} B^T P + Q = 0
///
/// Uses Hamiltonian matrix approach:
/// H = [ A    -B*R^{-1}*B^T ]
///     [ -Q       -A^T      ]
///
/// # Arguments
/// * `a` - State matrix (n × n)
/// * `b` - Input matrix (n × m)
/// * `q` - State cost matrix (n × n), must be positive semi-definite
/// * `r` - Input cost matrix (m × m), must be positive definite
///
/// # Returns
/// Solution matrix P (n × n), positive semi-definite
pub fn solve_care(
    a: &Array2<f64>,
    b: &Array2<f64>,
    q: &Array2<f64>,
    r: &Array2<f64>,
) -> Result<Array2<f64>, LQRError> {
    let n = a.nrows();
    let m = b.ncols();

    // Validate dimensions
    if a.ncols() != n {
        return Err(LQRError::DimensionError(
            format!("A must be square, got {}×{}", n, a.ncols())
        ));
    }
    if b.nrows() != n {
        return Err(LQRError::DimensionError(
            format!("B must have {} rows, got {}", n, b.nrows())
        ));
    }
    if q.nrows() != n || q.ncols() != n {
        return Err(LQRError::DimensionError(
            format!("Q must be {}×{}, got {}×{}", n, n, q.nrows(), q.ncols())
        ));
    }
    if r.nrows() != m || r.ncols() != m {
        return Err(LQRError::DimensionError(
            format!("R must be {}×{}, got {}×{}", m, m, r.nrows(), r.ncols())
        ));
    }

    // Compute R^{-1}
    let r_inv = r.inv().map_err(|_| {
        LQRError::PositiveDefiniteError("R must be positive definite".to_string())
    })?;

    // Compute B * R^{-1} * B^T
    let br = b.dot(&r_inv);
    let brbt = br.dot(&b.t());

    // Build Hamiltonian matrix H
    let mut h = Array2::<f64>::zeros((2 * n, 2 * n));

    // Top-left: A
    for i in 0..n {
        for j in 0..n {
            h[[i, j]] = a[[i, j]];
        }
    }

    // Top-right: -B*R^{-1}*B^T
    for i in 0..n {
        for j in 0..n {
            h[[i, j + n]] = -brbt[[i, j]];
        }
    }

    // Bottom-left: -Q
    for i in 0..n {
        for j in 0..n {
            h[[i + n, j]] = -q[[i, j]];
        }
    }

    // Bottom-right: -A^T
    for i in 0..n {
        for j in 0..n {
            h[[i + n, j + n]] = -a[[j, i]];
        }
    }

    // Compute eigendecomposition of H
    let (eigenvalues, eigenvectors) = h.eig().map_err(|_| {
        LQRError::ConvergenceError("Eigendecomposition failed".to_string())
    })?;

    // Select stable eigenvalues (negative real part)
    let mut stable_indices = Vec::new();
    for (i, &ev) in eigenvalues.iter().enumerate() {
        if ev.re < 0.0 {
            stable_indices.push(i);
        }
    }

    if stable_indices.len() != n {
        return Err(LQRError::ConvergenceError(
            format!("Expected {} stable eigenvalues, found {}", n, stable_indices.len())
        ));
    }

    // Extract stable eigenvectors
    let mut u1 = Array2::<f64>::zeros((n, n));
    let mut u2 = Array2::<f64>::zeros((n, n));

    for (col, &idx) in stable_indices.iter().enumerate() {
        for row in 0..n {
            u1[[row, col]] = eigenvectors[[row, idx]].re;
            u2[[row, col]] = eigenvectors[[row + n, idx]].re;
        }
    }

    // Compute P = U2 * U1^{-1}
    let u1_inv = u1.inv().map_err(|_| {
        LQRError::ConvergenceError("U1 matrix is singular".to_string())
    })?;

    let p = u2.dot(&u1_inv);

    // Symmetrize P (should be symmetric, but numerical errors may break this)
    let p_sym = 0.5 * (&p + &p.t());

    Ok(p_sym)
}

/// Compute LQR gain matrix
///
/// K = R^{-1} B^T P
pub fn compute_lqr_gain(
    b: &Array2<f64>,
    r: &Array2<f64>,
    p: &Array2<f64>,
) -> Result<Array2<f64>, LQRError> {
    let r_inv = r.inv().map_err(|_| {
        LQRError::PositiveDefiniteError("R must be positive definite".to_string())
    })?;

    let k = r_inv.dot(&b.t()).dot(p);
    Ok(k)
}

/// LQR Controller with Python bindings
#[pyclass]
pub struct LQRController {
    /// Optimal gain matrix K
    k: DMatrix<f64>,

    /// State dimension
    n: usize,

    /// Input dimension
    m: usize,

    /// Solution to CARE
    p: DMatrix<f64>,
}

#[pymethods]
impl LQRController {
    /// Create new LQR controller
    ///
    /// # Arguments
    /// * `a` - State matrix (n × n)
    /// * `b` - Input matrix (n × m)
    /// * `q` - State cost matrix (n × n)
    /// * `r` - Input cost matrix (m × m)
    ///
    /// # Returns
    /// LQR controller with computed optimal gain
    #[new]
    pub fn new(
        a: PyReadonlyArray2<f64>,
        b: PyReadonlyArray2<f64>,
        q: PyReadonlyArray2<f64>,
        r: PyReadonlyArray2<f64>,
    ) -> PyResult<Self> {
        let a_arr = a.as_array().to_owned();
        let b_arr = b.as_array().to_owned();
        let q_arr = q.as_array().to_owned();
        let r_arr = r.as_array().to_owned();

        let n = a_arr.nrows();
        let m = b_arr.ncols();

        // Solve CARE
        let p_arr = solve_care(&a_arr, &b_arr, &q_arr, &r_arr)?;

        // Compute gain
        let k_arr = compute_lqr_gain(&b_arr, &r_arr, &p_arr)?;

        // Convert to nalgebra
        let k = DMatrix::from_row_slice(k_arr.nrows(), k_arr.ncols(), k_arr.as_slice().unwrap());
        let p = DMatrix::from_row_slice(p_arr.nrows(), p_arr.ncols(), p_arr.as_slice().unwrap());

        Ok(Self { k, n, m, p })
    }

    /// Compute control input: u = -K * x
    ///
    /// # Arguments
    /// * `state` - Current state vector (n,)
    ///
    /// # Returns
    /// Control input vector (m,)
    pub fn compute_control<'py>(
        &self,
        py: Python<'py>,
        state: PyReadonlyArray1<f64>,
    ) -> PyResult<&'py PyArray1<f64>> {
        let x = state.as_array();

        if x.len() != self.n {
            return Err(PyValueError::new_err(
                format!("State must have length {}, got {}", self.n, x.len())
            ));
        }

        // Convert to nalgebra
        let x_vec = DVector::from_row_slice(x.as_slice().unwrap());

        // u = -K * x
        let u = -&self.k * x_vec;

        // Convert back to numpy
        Ok(PyArray1::from_vec(py, u.as_slice().to_vec()))
    }

    /// Get the optimal gain matrix
    #[getter]
    pub fn gain<'py>(&self, py: Python<'py>) -> &'py PyArray2<f64> {
        let data = self.k.as_slice().to_vec();
        PyArray2::from_vec2(py, &vec![data; 1].into_iter()
            .flat_map(|row| row.into_iter())
            .collect::<Vec<_>>()
            .chunks(self.n)
            .map(|chunk| chunk.to_vec())
            .collect::<Vec<_>>())
            .unwrap()
    }

    /// Get the CARE solution matrix P
    #[getter]
    pub fn p_matrix<'py>(&self, py: Python<'py>) -> &'py PyArray2<f64> {
        let data = self.p.as_slice().to_vec();
        PyArray2::from_vec2(py, &vec![data; 1].into_iter()
            .flat_map(|row| row.into_iter())
            .collect::<Vec<_>>()
            .chunks(self.n)
            .map(|chunk| chunk.to_vec())
            .collect::<Vec<_>>())
            .unwrap()
    }

    /// Compute closed-loop eigenvalues
    ///
    /// Returns eigenvalues of (A - B*K)
    pub fn closed_loop_eigenvalues<'py>(
        &self,
        py: Python<'py>,
        a: PyReadonlyArray2<f64>,
        b: PyReadonlyArray2<f64>,
    ) -> PyResult<&'py PyArray1<f64>> {
        let a_arr = a.as_array().to_owned();
        let b_arr = b.as_array().to_owned();

        // Convert K to ndarray
        let k_arr = Array2::from_shape_vec(
            (self.k.nrows(), self.k.ncols()),
            self.k.as_slice().to_vec()
        ).unwrap();

        // Compute A - B*K
        let bk = b_arr.dot(&k_arr);
        let a_cl = a_arr - bk;

        // Compute eigenvalues
        let (eigs, _) = a_cl.eig().map_err(|_| {
            PyValueError::new_err("Eigenvalue computation failed")
        })?;

        // Return real parts (for stability check)
        let real_parts: Vec<f64> = eigs.iter().map(|e| e.re).collect();
        Ok(PyArray1::from_vec(py, real_parts))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;

    #[test]
    fn test_care_simple() {
        // Simple 1D system: dx/dt = a*x + b*u
        let a = array![[1.0]];
        let b = array![[1.0]];
        let q = array![[1.0]];
        let r = array![[1.0]];

        let p = solve_care(&a, &b, &q, &r).unwrap();

        // For this system, P = sqrt(2) - 1 ≈ 0.414
        assert!((p[[0, 0]] - 0.414).abs() < 0.01);
    }

    #[test]
    fn test_care_2d() {
        // Double integrator: dx/dt = [0 1; 0 0]*x + [0; 1]*u
        let a = array![[0.0, 1.0], [0.0, 0.0]];
        let b = array![[0.0], [1.0]];
        let q = array![[1.0, 0.0], [0.0, 1.0]];
        let r = array![[1.0]];

        let p = solve_care(&a, &b, &q, &r).unwrap();

        // P should be positive definite
        assert!(p[[0, 0]] > 0.0);
        assert!(p[[1, 1]] > 0.0);
        assert!(p[[0, 0]] * p[[1, 1]] > p[[0, 1]] * p[[1, 0]]);
    }

    #[test]
    fn test_lqr_gain() {
        let a = array![[0.0, 1.0], [0.0, 0.0]];
        let b = array![[0.0], [1.0]];
        let q = array![[1.0, 0.0], [0.0, 1.0]];
        let r = array![[1.0]];

        let p = solve_care(&a, &b, &q, &r).unwrap();
        let k = compute_lqr_gain(&b, &r, &p).unwrap();

        // K should have correct dimensions
        assert_eq!(k.shape(), &[1, 2]);

        // Both gains should be positive (stabilizing)
        assert!(k[[0, 0]] > 0.0);
        assert!(k[[0, 1]] > 0.0);
    }
}
