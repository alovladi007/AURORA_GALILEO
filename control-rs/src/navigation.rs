/*!
Navigation filters (EKF, UKF)
*/

use pyo3::prelude::*;

#[pyclass]
pub struct EKF {
    // Placeholder
}

#[pymethods]
impl EKF {
    #[new]
    pub fn new() -> Self {
        Self {}
    }
}
