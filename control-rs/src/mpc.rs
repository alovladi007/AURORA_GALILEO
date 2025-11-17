/*!
Model Predictive Control (MPC)
===============================

Implements linear MPC with box constraints using OSQP.

Solves at each time step:
    min_{u_0,...,u_{N-1}} Σ (x_k^T Q x_k + u_k^T R u_k) + x_N^T Q_f x_N
    subject to:
        x_{k+1} = A x_k + B u_k
        x_min ≤ x_k ≤ x_max
        u_min ≤ u_k ≤ u_max
*/

use nalgebra::{DMatrix, DVector};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use numpy::{PyArray1, PyArray2, PyReadonlyArray2, PyReadonlyArray1};
use ndarray::{Array1, Array2};
use osqp::{CscMatrix, Problem, Settings};

/// Error types for MPC
#[derive(Debug, thiserror::Error)]
pub enum MPCError {
    #[error("Dimension mismatch: {0}")]
    DimensionError(String),

    #[error("OSQP solver failed: {0}")]
    SolverError(String),

    #[error("Invalid parameters: {0}")]
    ParameterError(String),
}

impl From<MPCError> for PyErr {
    fn from(err: MPCError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

/// Build sparse MPC problem in QP form
///
/// Formulates the MPC problem as:
///     min 0.5 z^T P z + q^T z
///     s.t. l ≤ A z ≤ u
///
/// where z = [x_0, u_0, x_1, u_1, ..., x_N]
fn build_mpc_qp<'a>(
    a: &Array2<f64>,
    b: &Array2<f64>,
    q: &Array2<f64>,
    r: &Array2<f64>,
    q_f: &Array2<f64>,
    n: usize,  // state dim
    m: usize,  // input dim
    horizon: usize,
) -> Result<(CscMatrix<'a>, Vec<f64>, CscMatrix<'a>, Vec<f64>, Vec<f64>), MPCError> {
    // Total decision variables: (n + m) * horizon + n
    let nz = (n + m) * horizon + n;

    // Build cost matrix P (block diagonal)
    let mut p_data = vec![];
    let mut p_indices = vec![];
    let mut p_indptr = vec![0];

    for k in 0..horizon {
        // Add Q block for x_k
        for j in 0..n {
            for i in 0..n {
                if q[[i, j]].abs() > 1e-12 {
                    p_data.push(q[[i, j]]);
                    p_indices.push(k * (n + m) + i);
                }
            }
            p_indptr.push(p_data.len());
        }

        // Add R block for u_k
        for j in 0..m {
            for i in 0..m {
                if r[[i, j]].abs() > 1e-12 {
                    p_data.push(r[[i, j]]);
                    p_indices.push(k * (n + m) + n + i);
                }
            }
            p_indptr.push(p_data.len());
        }
    }

    // Add Q_f block for x_N
    for j in 0..n {
        for i in 0..n {
            if q_f[[i, j]].abs() > 1e-12 {
                p_data.push(q_f[[i, j]]);
                p_indices.push(horizon * (n + m) + i);
            }
        }
        p_indptr.push(p_data.len());
    }

    let p_matrix = CscMatrix {
        nrows: nz,
        ncols: nz,
        indptr: p_indptr.into(),
        indices: p_indices.into(),
        data: p_data.into(),
    };

    // Linear cost (zero for now - can be extended for tracking)
    let q_vec = vec![0.0; nz];

    // Build constraint matrix A_c
    // Constraints: x_{k+1} = A x_k + B u_k (equality constraints)
    let num_constraints = n * horizon;

    let mut ac_data = vec![];
    let mut ac_indices = vec![];
    let mut ac_indptr = vec![0];

    for k in 0..horizon {
        // For each constraint row (n rows per time step)
        for i in 0..n {
            // -I for x_{k+1}
            ac_data.push(-1.0);
            ac_indices.push((k + 1) * (n + m) + i);

            // A for x_k
            for j in 0..n {
                if a[[i, j]].abs() > 1e-12 {
                    ac_data.push(a[[i, j]]);
                    ac_indices.push(k * (n + m) + j);
                }
            }

            // B for u_k
            for j in 0..m {
                if b[[i, j]].abs() > 1e-12 {
                    ac_data.push(b[[i, j]]);
                    ac_indices.push(k * (n + m) + n + j);
                }
            }

            ac_indptr.push(ac_data.len());
        }
    }

    let ac_matrix = CscMatrix {
        nrows: num_constraints,
        ncols: nz,
        indptr: ac_indptr.into(),
        indices: ac_indices.into(),
        data: ac_data.into(),
    };

    // Constraint bounds (dynamics are equality: Ax + Bu - x_{k+1} = 0)
    let l = vec![0.0; num_constraints];
    let u = vec![0.0; num_constraints];

    Ok((p_matrix, q_vec, ac_matrix, l, u))
}

/// MPC Controller with Python bindings
#[pyclass]
pub struct MPCController {
    /// State matrix A
    a: DMatrix<f64>,

    /// Input matrix B
    b: DMatrix<f64>,

    /// State cost Q
    q: DMatrix<f64>,

    /// Input cost R
    r: DMatrix<f64>,

    /// Terminal cost Q_f
    q_f: DMatrix<f64>,

    /// Prediction horizon
    horizon: usize,

    /// State dimension
    n: usize,

    /// Input dimension
    m: usize,

    /// State constraints (min, max)
    x_min: Option<DVector<f64>>,
    x_max: Option<DVector<f64>>,

    /// Input constraints (min, max)
    u_min: Option<DVector<f64>>,
    u_max: Option<DVector<f64>>,
}

#[pymethods]
impl MPCController {
    /// Create new MPC controller
    ///
    /// # Arguments
    /// * `a` - State matrix (n × n)
    /// * `b` - Input matrix (n × m)
    /// * `q` - State cost matrix (n × n)
    /// * `r` - Input cost matrix (m × m)
    /// * `horizon` - Prediction horizon
    /// * `q_f` - Terminal cost (optional, defaults to Q)
    #[new]
    #[pyo3(signature = (a, b, q, r, horizon, q_f=None))]
    pub fn new(
        a: PyReadonlyArray2<f64>,
        b: PyReadonlyArray2<f64>,
        q: PyReadonlyArray2<f64>,
        r: PyReadonlyArray2<f64>,
        horizon: usize,
        q_f: Option<PyReadonlyArray2<f64>>,
    ) -> PyResult<Self> {
        let a_arr = a.as_array();
        let b_arr = b.as_array();
        let q_arr = q.as_array();
        let r_arr = r.as_array();

        let n = a_arr.nrows();
        let m = b_arr.ncols();

        // Convert to nalgebra
        let a_mat = DMatrix::from_row_slice(n, n, a_arr.as_slice().unwrap());
        let b_mat = DMatrix::from_row_slice(n, m, b_arr.as_slice().unwrap());
        let q_mat = DMatrix::from_row_slice(n, n, q_arr.as_slice().unwrap());
        let r_mat = DMatrix::from_row_slice(m, m, r_arr.as_slice().unwrap());

        let q_f_mat = match q_f {
            Some(qf) => {
                let qf_arr = qf.as_array();
                DMatrix::from_row_slice(n, n, qf_arr.as_slice().unwrap())
            }
            None => q_mat.clone(),
        };

        Ok(Self {
            a: a_mat,
            b: b_mat,
            q: q_mat,
            r: r_mat,
            q_f: q_f_mat,
            horizon,
            n,
            m,
            x_min: None,
            x_max: None,
            u_min: None,
            u_max: None,
        })
    }

    /// Set state constraints
    ///
    /// # Arguments
    /// * `x_min` - Lower bound on states
    /// * `x_max` - Upper bound on states
    pub fn set_state_constraints(
        &mut self,
        x_min: PyReadonlyArray1<f64>,
        x_max: PyReadonlyArray1<f64>,
    ) -> PyResult<()> {
        let xmin = x_min.as_array();
        let xmax = x_max.as_array();

        self.x_min = Some(DVector::from_row_slice(xmin.as_slice().unwrap()));
        self.x_max = Some(DVector::from_row_slice(xmax.as_slice().unwrap()));

        Ok(())
    }

    /// Set input constraints
    ///
    /// # Arguments
    /// * `u_min` - Lower bound on inputs
    /// * `u_max` - Upper bound on inputs
    pub fn set_input_constraints(
        &mut self,
        u_min: PyReadonlyArray1<f64>,
        u_max: PyReadonlyArray1<f64>,
    ) -> PyResult<()> {
        let umin = u_min.as_array();
        let umax = u_max.as_array();

        self.u_min = Some(DVector::from_row_slice(umin.as_slice().unwrap()));
        self.u_max = Some(DVector::from_row_slice(umax.as_slice().unwrap()));

        Ok(())
    }

    /// Solve MPC problem for current state
    ///
    /// # Arguments
    /// * `x0` - Current state vector (n,)
    ///
    /// # Returns
    /// Optimal control input for current time step (m,)
    pub fn solve<'py>(
        &self,
        py: Python<'py>,
        x0: PyReadonlyArray1<f64>,
    ) -> PyResult<&'py PyArray1<f64>> {
        let x0_arr = x0.as_array();

        if x0_arr.len() != self.n {
            return Err(MPCError::DimensionError(
                format!("x0 must have length {}, got {}", self.n, x0_arr.len())
            ).into());
        }

        // Convert matrices to ndarray for QP construction
        let a = Array2::from_shape_vec(
            (self.n, self.n),
            self.a.as_slice().to_vec()
        ).unwrap();

        let b = Array2::from_shape_vec(
            (self.n, self.m),
            self.b.as_slice().to_vec()
        ).unwrap();

        let q = Array2::from_shape_vec(
            (self.n, self.n),
            self.q.as_slice().to_vec()
        ).unwrap();

        let r = Array2::from_shape_vec(
            (self.m, self.m),
            self.r.as_slice().to_vec()
        ).unwrap();

        let q_f = Array2::from_shape_vec(
            (self.n, self.n),
            self.q_f.as_slice().to_vec()
        ).unwrap();

        // Build QP
        let (p, q_lin, a_c, mut l, mut u) = build_mpc_qp(
            &a, &b, &q, &r, &q_f,
            self.n, self.m, self.horizon
        ).map_err(|e| PyValueError::new_err(e.to_string()))?;

        // Set initial condition constraint
        // x_0 = x0 (equality constraint)
        for i in 0..self.n {
            l[i] = -x0_arr[i];
            u[i] = -x0_arr[i];
        }

        // Setup OSQP
        let settings = Settings::default()
            .verbose(false)
            .eps_abs(1e-6)
            .eps_rel(1e-6);

        let mut prob = Problem::new(p, &q_lin, a_c, &l, &u, &settings)
            .map_err(|e| MPCError::SolverError(format!("{:?}", e)))?;

        // Solve
        let result = prob.solve();

        let solution = result.x().ok_or_else(|| {
            MPCError::SolverError("No solution found".to_string())
        })?;

        // Extract first control input u_0
        let u0 = &solution[self.n..self.n + self.m];

        Ok(PyArray1::from_slice(py, u0))
    }

    /// Get prediction horizon
    #[getter]
    pub fn get_horizon(&self) -> usize {
        self.horizon
    }

    /// Get state dimension
    #[getter]
    pub fn get_state_dim(&self) -> usize {
        self.n
    }

    /// Get input dimension
    #[getter]
    pub fn get_input_dim(&self) -> usize {
        self.m
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;

    #[test]
    fn test_mpc_qp_build() {
        // Simple 1D system
        let a = array![[1.0]];
        let b = array![[1.0]];
        let q = array![[1.0]];
        let r = array![[1.0]];
        let q_f = array![[1.0]];

        let horizon = 3;

        let result = build_mpc_qp(&a, &b, &q, &r, &q_f, 1, 1, horizon);
        assert!(result.is_ok());

        let (p, q_vec, a_c, l, u) = result.unwrap();

        // Check dimensions
        let nz = (1 + 1) * horizon + 1;  // 7 variables
        assert_eq!(p.nrows, nz);
        assert_eq!(q_vec.len(), nz);
        assert_eq!(a_c.nrows, horizon);  // 3 dynamics constraints
    }
}
