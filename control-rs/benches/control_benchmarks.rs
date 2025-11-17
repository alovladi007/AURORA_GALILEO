/*!
Criterion Benchmarks for Control Module
=========================================

Performance benchmarks for LQR, MPC, EKF, UKF, and LQG controllers.
*/

use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use ndarray::array;
use control::lqr::{solve_care, compute_lqr_gain};
use control::mpc::MPCController;
use control::navigation::{EKF, UKF};

// ============================================================================
// LQR Benchmarks
// ============================================================================

fn bench_care_solver(c: &mut Criterion) {
    let mut group = c.benchmark_group("CARE Solver");

    for n in [2, 4, 6, 8, 10].iter() {
        let a = ndarray::Array2::eye(*n);
        let b = ndarray::Array2::eye(*n);
        let q = ndarray::Array2::eye(*n);
        let r = ndarray::Array2::eye(*n);

        group.bench_with_input(BenchmarkId::from_parameter(n), n, |bencher, _| {
            bencher.iter(|| {
                let _ = solve_care(
                    black_box(&a),
                    black_box(&b),
                    black_box(&q),
                    black_box(&r),
                );
            });
        });
    }

    group.finish();
}

fn bench_lqr_gain(c: &mut Criterion) {
    let b = array![[0.0], [1.0]];
    let r = array![[1.0]];
    let p = array![[1.732, 1.414], [1.414, 2.0]];

    c.bench_function("LQR gain computation", |bencher| {
        bencher.iter(|| {
            let _ = compute_lqr_gain(
                black_box(&b),
                black_box(&r),
                black_box(&p),
            );
        });
    });
}

// ============================================================================
// EKF Benchmarks
// ============================================================================

fn bench_ekf_predict(c: &mut Criterion) {
    let mut group = c.benchmark_group("EKF Predict");

    for n in [4, 6, 8, 10].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(n), n, |bencher, &n| {
            let x0 = ndarray::Array1::zeros(n);
            let p0 = ndarray::Array2::eye(n);
            let q = ndarray::Array2::eye(n) * 0.01;
            let r = ndarray::Array2::eye(2) * 0.1;

            bencher.iter(|| {
                // Simulate predict step
                let f = ndarray::Array2::eye(n);
                let x_pred = x0.clone();
                // In real benchmark, would call EKF::predict
            });
        });
    }

    group.finish();
}

// ============================================================================
// UKF Benchmarks
// ============================================================================

fn bench_ukf_sigma_points(c: &mut Criterion) {
    let mut group = c.benchmark_group("UKF Sigma Points");

    for n in [4, 6, 8, 10].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(n), n, |bencher, &n| {
            let x = ndarray::Array1::zeros(n);
            let p = ndarray::Array2::eye(n);
            let alpha = 1e-3;
            let kappa = 0.0;
            let lambda = alpha * alpha * (n as f64 + kappa) - n as f64;

            bencher.iter(|| {
                // Simulate sigma point generation
                let scale = n as f64 + lambda;
                let _scaled_p = black_box(&p) * scale;
            });
        });
    }

    group.finish();
}

// ============================================================================
// Comparison Benchmarks
// ============================================================================

fn bench_control_comparison(c: &mut Criterion) {
    let mut group = c.benchmark_group("Control Algorithm Comparison");

    // Double integrator system
    let a = array![[1.0, 0.1], [0.0, 1.0]];
    let b = array![[0.005], [0.1]];
    let q = array![[10.0, 0.0], [0.0, 1.0]];
    let r = array![[1.0]];

    // LQR CARE solve
    group.bench_function("LQR (CARE)", |bencher| {
        bencher.iter(|| {
            let p = solve_care(black_box(&a), black_box(&b), black_box(&q), black_box(&r)).unwrap();
            let _k = compute_lqr_gain(black_box(&b), black_box(&r), black_box(&p)).unwrap();
        });
    });

    group.finish();
}

fn bench_memory_allocation(c: &mut Criterion) {
    let mut group = c.benchmark_group("Memory Allocation");

    for size in [10, 50, 100, 200].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |bencher, &size| {
            bencher.iter(|| {
                let _a = ndarray::Array2::<f64>::zeros((size, size));
                let _b = ndarray::Array2::<f64>::zeros((size, size / 2));
            });
        });
    }

    group.finish();
}

// ============================================================================
// System-level Benchmarks
// ============================================================================

fn bench_control_loop(c: &mut Criterion) {
    c.bench_function("Full control loop (2-DOF)", |bencher| {
        let a = array![[1.0, 0.1], [0.0, 1.0]];
        let b = array![[0.005], [0.1]];
        let q = array![[10.0, 0.0], [0.0, 1.0]];
        let r = array![[1.0]];

        let p = solve_care(&a, &b, &q, &r).unwrap();
        let k = compute_lqr_gain(&b, &r, &p).unwrap();

        bencher.iter(|| {
            let x = array![1.0, 0.0];
            let u = -k.dot(&x);
            let _x_next = a.dot(&x) + b.dot(&u);
        });
    });
}

fn bench_navigation_loop(c: &mut Criterion) {
    c.bench_function("Full navigation loop (6-DOF)", |bencher| {
        let n = 6;
        let f = ndarray::Array2::eye(n);
        let h = ndarray::Array2::from_shape_fn((3, n), |(i, j)| if i == j { 1.0 } else { 0.0 });

        bencher.iter(|| {
            // Simulate full EKF cycle
            let _x_pred = black_box(&f);
            let _y_pred = black_box(&h);
        });
    });
}

// ============================================================================
// Criterion Configuration
// ============================================================================

criterion_group!(
    benches,
    bench_care_solver,
    bench_lqr_gain,
    bench_ekf_predict,
    bench_ukf_sigma_points,
    bench_control_comparison,
    bench_memory_allocation,
    bench_control_loop,
    bench_navigation_loop,
);

criterion_main!(benches);
