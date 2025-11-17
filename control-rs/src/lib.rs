/*!
GALILEO V2.0 - Control Module (Rust + pyo3)
===========================================

High-performance GNC algorithms with Python bindings.

Modules:
- lqr: Linear Quadratic Regulator
- lqg: Linear Quadratic Gaussian
- mpc: Model Predictive Control
- navigation: EKF/UKF navigation filters
*/

use pyo3::prelude::*;

pub mod lqr;
pub mod lqg;
pub mod mpc;
pub mod navigation;

/// Python module initialization
#[pymodule]
fn control(_py: Python, m: &PyModule) -> PyResult<()> {
    // Control algorithms
    m.add_class::<lqr::LQRController>()?;
    m.add_class::<lqg::LQGController>()?;
    m.add_class::<mpc::MPCController>()?;

    // Navigation filters
    m.add_class::<navigation::EKF>()?;
    m.add_class::<navigation::UKF>()?;

    Ok(())
}
