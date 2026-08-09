"""
Orbital propagators module.

Implements numerical integration methods for propagating orbital dynamics:
- RK4 (4th-order Runge-Kutta)
- Adaptive step-size methods (future work: RKF45, Dormand-Prince)

All propagators work with JAX arrays and can be JIT-compiled or vmapped
for batch processing.
"""

from typing import Callable, Tuple
import jax
import jax.numpy as jnp
from jax import Array


def rk4_step(
    dynamics_func: Callable[[float, Array], Array],
    t: float,
    state: Array,
    dt: float
) -> Array:
    """
    Single step of 4th-order Runge-Kutta (RK4) integration.
    
    RK4 is a classic explicit integrator with 4th-order accuracy. It's
    suitable for most orbital propagation tasks and offers a good balance
    between accuracy and computational cost.
    
    Algorithm:
        k1 = f(t, y)
        k2 = f(t + dt/2, y + dt/2 * k1)
        k3 = f(t + dt/2, y + dt/2 * k2)
        k4 = f(t + dt, y + dt * k3)
        y_next = y + dt/6 * (k1 + 2*k2 + 2*k3 + k4)
    
    Local truncation error: O(dt⁵)
    Global error: O(dt⁴)
    
    Args:
        dynamics_func: Function that computes dy/dt given (t, y)
        t: Current time (s)
        state: Current state vector
        dt: Time step (s)
    
    Returns:
        Next state vector at time t + dt
    
    Example:
        >>> from sim.dynamics.keplerian import two_body_dynamics
        >>> state = jnp.array([7000.0, 0.0, 0.0, 0.0, 7.5, 0.0])
        >>> next_state = rk4_step(two_body_dynamics, 0.0, state, 10.0)
    """
    # Compute RK4 stages
    k1 = dynamics_func(t, state)
    k2 = dynamics_func(t + 0.5 * dt, state + 0.5 * dt * k1)
    k3 = dynamics_func(t + 0.5 * dt, state + 0.5 * dt * k2)
    k4 = dynamics_func(t + dt, state + dt * k3)
    
    # Combine stages for next state
    next_state = state + (dt / 6.0) * (k1 + 2*k2 + 2*k3 + k4)
    
    return next_state


def propagate_orbit(
    dynamics_func: Callable[[float, Array], Array],
    initial_state: Array,
    t_span: Tuple[float, float],
    dt: float,
    save_every: int = 1
) -> Tuple[Array, Array]:
    """
    Propagate orbital state over a time interval using RK4.
    
    Integrates the equations of motion from t0 to tf, saving states at
    regular intervals. Uses fixed-step RK4 integration.
    
    Args:
        dynamics_func: Dynamics function dy/dt = f(t, y)
        initial_state: Initial state vector
        t_span: Tuple of (t_start, t_end) in seconds
        dt: Integration time step (s)
        save_every: Save state every N steps (default: 1 = save all)
    
    Returns:
        Tuple of (times, states):
            - times: Array of time points (s)
            - states: Array of state vectors, shape (n_saves, state_dim)
    
    Note:
        For long propagations or high accuracy requirements, consider using
        an adaptive step-size method (RKF45, Dormand-Prince) which will be
        added in future versions.
    
    Example:
        >>> from sim.dynamics.keplerian import two_body_dynamics
        >>> state0 = jnp.array([7000.0, 0.0, 0.0, 0.0, 7.5, 0.0])
        >>> times, states = propagate_orbit(
        ...     two_body_dynamics,
        ...     state0,
        ...     t_span=(0.0, 5400.0),  # 90 minutes
        ...     dt=10.0
        ... )
    """
    t0, tf = t_span
    n_steps = int((tf - t0) / dt)
    n_saves = n_steps // save_every + 1
    
    # Pre-allocate arrays
    times = jnp.linspace(t0, tf, n_saves)
    states = jnp.zeros((n_saves, len(initial_state)))
    
    # Initial condition
    states = states.at[0].set(initial_state)
    
    # Propagation loop
    t = t0
    state = initial_state
    save_idx = 1
    
    for step in range(n_steps):
        # RK4 step
        state = rk4_step(dynamics_func, t, state, dt)
        t += dt
        
        # Save if needed
        if (step + 1) % save_every == 0 and save_idx < n_saves:
            states = states.at[save_idx].set(state)
            save_idx += 1
    
    return times, states


def propagate_orbit_jax(
    dynamics_func: Callable[[float, Array], Array],
    initial_state: Array,
    t_span: Tuple[float, float],
    dt: float
) -> Tuple[Array, Array]:
    """
    Propagate orbit using JAX's scan for better performance.
    
    This version uses jax.lax.scan which is more efficient than Python loops
    and can be JIT-compiled. It's particularly beneficial for:
    - Long propagations
    - Batch processing (with vmap)
    - Gradient computation (with grad)
    
    Args:
        dynamics_func: Dynamics function dy/dt = f(t, y)
        initial_state: Initial state vector
        t_span: Tuple of (t_start, t_end) in seconds
        dt: Integration time step (s)
    
    Returns:
        Tuple of (times, states):
            - times: Array of time points (s)
            - states: Array of state vectors, shape (n_steps+1, state_dim)
    
    Example:
        >>> from sim.dynamics.keplerian import two_body_dynamics
        >>> state0 = jnp.array([7000.0, 0.0, 0.0, 0.0, 7.5, 0.0])
        >>> times, states = propagate_orbit_jax(
        ...     two_body_dynamics,
        ...     state0,
        ...     t_span=(0.0, 5400.0),
        ...     dt=10.0
        ... )
    """
    t0, tf = t_span
    times = jnp.arange(t0, tf + dt, dt)
    
    def step_fn(state, t):
        next_state = rk4_step(dynamics_func, t, state, dt)
        return next_state, next_state
    
    _, states = jax.lax.scan(step_fn, initial_state, times[:-1])
    
    # Prepend initial state
    states = jnp.vstack([initial_state, states])
    
    return times, states


def propagate_relative_orbit(
    delta_state: Array,
    n: float,
    t_span: Tuple[float, float],
    dt: float
) -> Tuple[Array, Array]:
    """
    Propagate relative orbital motion using Hill-Clohessy-Wiltshire equations.
    
    Specialized propagator for formation flying dynamics using the linearized
    CW equations. This is computationally efficient and accurate for small
    relative separations.
    
    Args:
        delta_state: Initial relative state [δx, δy, δz, δvx, δvy, δvz] (km, km/s)
        n: Mean motion of leader orbit (rad/s)
        t_span: Tuple of (t_start, t_end) in seconds
        dt: Integration time step (s)
    
    Returns:
        Tuple of (times, delta_states):
            - times: Array of time points (s)
            - delta_states: Array of relative states
    
    Example:
        >>> # 1 km radial separation, circular relative orbit
        >>> delta_state = jnp.array([1.0, 0.0, 0.0, 0.0, 0.001, 0.0])
        >>> n = 0.001  # rad/s
        >>> times, states = propagate_relative_orbit(
        ...     delta_state, n, t_span=(0.0, 6000.0), dt=10.0
        ... )
    """
    from .relative import hill_clohessy_wiltshire_dynamics
    
    def dynamics_wrapper(t, state):
        return hill_clohessy_wiltshire_dynamics(t, state, n)
    
    return propagate_orbit_jax(dynamics_wrapper, delta_state, t_span, dt)


# JIT-compile for performance. t_span/dt must be static: they size
# jnp.arange / the scan length, which cannot depend on traced values
# (previously every call raised ConcretizationTypeError).
rk4_step = jax.jit(rk4_step, static_argnames=['dynamics_func'])
propagate_orbit_jax = jax.jit(
    propagate_orbit_jax, static_argnames=['dynamics_func', 't_span', 'dt']
)
propagate_relative_orbit = jax.jit(
    propagate_relative_orbit, static_argnames=['t_span', 'dt']
)
