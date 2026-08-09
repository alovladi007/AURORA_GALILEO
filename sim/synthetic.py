"""
Synthetic Interferometric Data Generator

Generates realistic interferometric time-series data with procedural subsurface anomalies.
Implements forward model: Δρ → Δg → baseline dynamics → interferometric phase → telemetry
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import json
from datetime import datetime, timedelta
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import warnings

# Physical constants
G = 6.67430e-11  # Gravitational constant (m³/kg·s²)
LAMBDA = 0.056  # C-band wavelength (m)
C = 299792458  # Speed of light (m/s)


@dataclass
class Anomaly:
    """Represents a subsurface anomaly"""
    type: str  # 'void', 'tunnel', 'ore'
    center: np.ndarray  # (x, y, z) in meters
    size: np.ndarray  # (dx, dy, dz) dimensions
    density_contrast: float  # kg/m³
    shape_params: Dict[str, float]  # Additional shape parameters
    

@dataclass
class SatelliteConfig:
    """Satellite constellation configuration"""
    num_satellites: int = 2
    orbital_height: float = 500e3  # meters
    baseline_nominal: float = 200.0  # meters
    baseline_variation: float = 10.0  # meters (1-sigma, RAW orbital)
    # Residual baseline error AFTER precise-orbit correction (m). The
    # raw ~10 m orbital variation is removed with POD ephemerides in
    # any real interferometric processor; only this residual reaches
    # the differential phase (cm-level for POD-corrected baselines).
    orbit_correction_residual: float = 0.01
    inclination: float = 97.4  # degrees (SSO)
    revisit_time: int = 12  # days
    

@dataclass
class SimulationConfig:
    """Simulation parameters"""
    grid_size: Tuple[int, int, int] = (100, 100, 50)  # (nx, ny, nz)
    grid_spacing: float = 10.0  # meters
    time_steps: int = 100
    time_interval: float = 1.0  # days
    seed: Optional[int] = None
    noise_level: float = 0.1  # radians
    atmospheric_noise: float = 0.05  # radians
    thermal_noise: float = 0.03  # radians
    layer_variation: float = 20.0  # kg/m³ (random sedimentary-layer noise)
    

class SubsurfaceModel:
    """Generates procedural subsurface anomalies"""
    
    def __init__(self, config: SimulationConfig, seed: Optional[int] = None):
        self.config = config
        self.rng = np.random.RandomState(seed)
        self.anomalies: List[Anomaly] = []
        self.density_field = None
        self._initialize_density_field()
        
    def _initialize_density_field(self):
        """Initialize background density field"""
        nx, ny, nz = self.config.grid_size
        # Background density with slight variations (sedimentary layers)
        self.density_field = np.zeros((nx, ny, nz))
        
        # Add sedimentary layers
        for z in range(nz):
            depth = z * self.config.grid_spacing
            base_density = 2000 + depth * 0.5  # Increasing with depth
            if self.config.layer_variation > 0:
                layer_variation = self.rng.normal(
                    0, self.config.layer_variation, (nx, ny))
            else:
                layer_variation = 0.0
            self.density_field[:, :, z] = base_density + layer_variation
            
    def add_void(self, center: Optional[np.ndarray] = None, 
                 size: Optional[np.ndarray] = None) -> Anomaly:
        """Add a void/cavity anomaly"""
        if center is None:
            nx, ny, nz = self.config.grid_size
            center = self.rng.uniform(
                [nx*0.2, ny*0.2, nz*0.3],
                [nx*0.8, ny*0.8, nz*0.9]
            ) * self.config.grid_spacing
            
        if size is None:
            size = self.rng.uniform([20, 20, 10], [50, 50, 20])
            
        anomaly = Anomaly(
            type='void',
            center=center,
            size=size,
            density_contrast=-2000,  # Air vs rock
            shape_params={'roughness': self.rng.uniform(0.1, 0.3)}
        )
        self.anomalies.append(anomaly)
        self._apply_anomaly(anomaly)
        return anomaly
        
    def add_tunnel(self, start: Optional[np.ndarray] = None,
                   end: Optional[np.ndarray] = None,
                   radius: float = 5.0) -> Anomaly:
        """Add a tunnel anomaly"""
        nx, ny, nz = self.config.grid_size
        
        if start is None:
            start = np.array([
                self.rng.uniform(nx*0.1, nx*0.3),
                self.rng.uniform(ny*0.1, ny*0.3),
                self.rng.uniform(nz*0.5, nz*0.7)
            ]) * self.config.grid_spacing
            
        if end is None:
            end = np.array([
                self.rng.uniform(nx*0.7, nx*0.9),
                self.rng.uniform(ny*0.7, ny*0.9),
                start[2] / self.config.grid_spacing + self.rng.uniform(-5, 5)
            ]) * self.config.grid_spacing
            
        center = (start + end) / 2
        size = np.array([
            np.linalg.norm(end - start),
            radius * 2,
            radius * 2
        ])
        
        anomaly = Anomaly(
            type='tunnel',
            center=center,
            size=size,
            density_contrast=-1800,  # Partially filled
            shape_params={
                'start': start.tolist(),
                'end': end.tolist(),
                'radius': radius
            }
        )
        self.anomalies.append(anomaly)
        self._apply_anomaly(anomaly)
        return anomaly
        
    def add_ore_body(self, center: Optional[np.ndarray] = None,
                     size: Optional[np.ndarray] = None,
                     density_contrast: Optional[float] = None) -> Anomaly:
        """Add a dense ore body anomaly"""
        if center is None:
            nx, ny, nz = self.config.grid_size
            center = self.rng.uniform(
                [nx*0.3, ny*0.3, nz*0.4],
                [nx*0.7, ny*0.7, nz*0.8]
            ) * self.config.grid_spacing
            
        if size is None:
            size = self.rng.uniform([30, 30, 15], [60, 60, 30])
            
        if density_contrast is None:
            # Various ore types
            density_contrast = self.rng.choice([500, 800, 1200, 2000])
            
        anomaly = Anomaly(
            type='ore',
            center=center,
            size=size,
            density_contrast=density_contrast,
            shape_params={
                'irregularity': self.rng.uniform(0.2, 0.5),
                'dip': self.rng.uniform(0, 90),  # degrees
                'strike': self.rng.uniform(0, 360)  # degrees
            }
        )
        self.anomalies.append(anomaly)
        self._apply_anomaly(anomaly)
        return anomaly
        
    def _apply_anomaly(self, anomaly: Anomaly):
        """Apply anomaly to density field"""
        nx, ny, nz = self.config.grid_size
        spacing = self.config.grid_spacing
        
        # Create grid
        x = np.arange(nx) * spacing
        y = np.arange(ny) * spacing
        z = np.arange(nz) * spacing
        X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
        
        if anomaly.type == 'void':
            # Ellipsoidal void with roughness
            dist = np.sqrt(
                ((X - anomaly.center[0]) / (anomaly.size[0]/2))**2 +
                ((Y - anomaly.center[1]) / (anomaly.size[1]/2))**2 +
                ((Z - anomaly.center[2]) / (anomaly.size[2]/2))**2
            )
            
            # Add roughness
            roughness = anomaly.shape_params['roughness']
            noise = self.rng.normal(0, roughness, dist.shape)
            mask = dist + noise < 1.0
            
        elif anomaly.type == 'tunnel':
            # Cylindrical tunnel
            start = np.array(anomaly.shape_params['start'])
            end = np.array(anomaly.shape_params['end'])
            radius = anomaly.shape_params['radius']
            
            # Vector along tunnel
            v = end - start
            v_norm = v / np.linalg.norm(v)
            
            # Distance to tunnel axis
            points = np.stack([X, Y, Z], axis=-1)
            to_start = points - start
            proj_length = np.dot(to_start, v_norm)
            proj_point = start + proj_length[..., np.newaxis] * v_norm
            dist_to_axis = np.linalg.norm(points - proj_point, axis=-1)
            
            # Check if within tunnel bounds
            mask = (dist_to_axis < radius) & (proj_length >= 0) & (proj_length <= np.linalg.norm(v))
            
        elif anomaly.type == 'ore':
            # Irregular ore body with dip and strike
            dip = np.radians(anomaly.shape_params['dip'])
            strike = np.radians(anomaly.shape_params['strike'])
            
            # Rotation matrix
            R_strike = np.array([
                [np.cos(strike), -np.sin(strike), 0],
                [np.sin(strike), np.cos(strike), 0],
                [0, 0, 1]
            ])
            R_dip = np.array([
                [1, 0, 0],
                [0, np.cos(dip), -np.sin(dip)],
                [0, np.sin(dip), np.cos(dip)]
            ])
            R = R_strike @ R_dip
            
            # Rotate coordinates
            points = np.stack([X - anomaly.center[0], 
                             Y - anomaly.center[1], 
                             Z - anomaly.center[2]], axis=-1)
            rotated = np.tensordot(points, R.T, axes=1)
            
            # Irregular ellipsoid
            irregularity = anomaly.shape_params['irregularity']
            noise_field = self.rng.normal(0, irregularity, rotated.shape[:-1])
            
            dist = np.sqrt(
                (rotated[..., 0] / (anomaly.size[0]/2))**2 +
                (rotated[..., 1] / (anomaly.size[1]/2))**2 +
                (rotated[..., 2] / (anomaly.size[2]/2))**2
            )
            mask = dist + noise_field < 1.0
            
        else:
            mask = np.zeros((nx, ny, nz), dtype=bool)
            
        # Apply density contrast
        self.density_field[mask] += anomaly.density_contrast
        

class ForwardModel:
    """Forward model for interferometric measurements"""
    
    def __init__(self, subsurface: SubsurfaceModel, 
                 sat_config: SatelliteConfig,
                 sim_config: SimulationConfig):
        self.subsurface = subsurface
        self.sat_config = sat_config
        self.sim_config = sim_config
        self.rng = np.random.RandomState(sim_config.seed)
        
    def density_to_gravity(self) -> np.ndarray:
        """Surface gravity anomaly (vertical component, m/s^2) from the
        3-D density model via Newtonian point-mass summation.

        For each depth layer, the density contrast (relative to the
        layer mean, i.e. the stratified background) is convolved with
        the Newtonian kernel

            K(dx, dy; z) = G dV z / (dx^2 + dy^2 + z^2)^{3/2}

        where z is the vertical distance from the source cell to the
        observation plane (one grid spacing above the surface — a
        ground/near-surface anomaly map; upward continuation to
        satellite altitude is an L1-processing step, not done here).
        The layer convolutions are evaluated with FFTs, which is exact
        for the periodic extension and O(nz * nx ny log(nx ny)).
        """
        from scipy.signal import fftconvolve

        density = self.subsurface.density_field
        nx, ny, nz = density.shape
        spacing = self.sim_config.grid_spacing

        # Observation plane just above the surface
        h_obs = spacing
        dV = spacing**3

        # Kernel support: offsets out to the full grid (linear
        # convolution via fftconvolve 'same' with a (2nx-1, 2ny-1) kernel)
        x_off = (np.arange(-(nx - 1), nx)) * spacing
        y_off = (np.arange(-(ny - 1), ny)) * spacing
        DX, DY = np.meshgrid(x_off, y_off, indexing="ij")

        g_field = np.zeros((nx, ny))
        for k in range(nz):
            layer = density[:, :, k]
            rho_contrast = layer - layer.mean()  # anomaly vs stratified bg
            if np.max(np.abs(rho_contrast)) < 1e-9:
                continue
            z = h_obs + k * spacing  # vertical lever arm to source layer
            r3 = (DX**2 + DY**2 + z**2) ** 1.5
            kernel = G * dV * z / r3
            g_field += fftconvolve(rho_contrast, kernel, mode="same")

        return g_field
        
    def gravity_to_baseline(self, g_field: np.ndarray,
                          time_steps: int) -> np.ndarray:
        """Convert the gravity anomaly map to baseline dynamics (m).

        Physical model: the two satellites, separated by the nominal
        baseline b0 along-track, feel a DIFFERENTIAL acceleration
        dg = (d g / d x) * b0. Under the linearized relative dynamics
        the quasi-static baseline response to a constant differential
        acceleration is dg / n^2 (forced HCW solution at DC), with n
        the orbital mean motion. All quantities are SI (meters).
        """
        nx, ny = g_field.shape
        baselines = np.zeros((time_steps, nx, ny))

        # Nominal baseline (m) and mean motion (rad/s) of the orbit
        b0 = self.sat_config.baseline_nominal
        GM = 3.986004418e14
        r_orbit = 6378137.0 + self.sat_config.orbital_height
        n_orbit = np.sqrt(GM / r_orbit**3)

        # Along-track gravity gradient (m/s^2 per m) -> differential
        # acceleration over the baseline -> quasi-static displacement
        spacing = self.sim_config.grid_spacing
        grad_g = np.gradient(g_field, spacing)[0]
        delta_b = (grad_g * b0) / n_orbit**2  # meters

        for t in range(time_steps):
            # Residual (post-POD-correction) orbital baseline error.
            # The raw baseline_variation (~10 m) would produce hundreds
            # of fringes per epoch at lambda=5.6 cm; interferometric
            # processing removes it with precise orbits, leaving only
            # orbit_correction_residual in the measured phase.
            orbital_phase = 2 * np.pi * t / 30  # Monthly variation
            orbital_var = (self.sat_config.orbit_correction_residual
                           * np.sin(orbital_phase))

            baselines[t] = b0 + delta_b + orbital_var

        return baselines
        
    def baseline_to_phase(self, baselines: np.ndarray) -> np.ndarray:
        """Convert baseline changes to interferometric phase"""
        # Phase sensitivity to baseline
        sensitivity = 2 * np.pi / LAMBDA  # rad/m
        
        # Reference baseline
        b_ref = baselines[0]
        
        # Phase time series
        phases = np.zeros_like(baselines)
        
        for t in range(baselines.shape[0]):
            # Differential phase (baselines are in meters end-to-end)
            delta_b = baselines[t] - b_ref
            phases[t] = sensitivity * delta_b

        return phases
        
    def add_noise(self, phases: np.ndarray) -> np.ndarray:
        """Add realistic noise to phase measurements"""
        noisy_phases = phases.copy()
        time_steps, nx, ny = phases.shape

        # noise_level acts as the master noise scale: atmospheric and
        # thermal amplitudes are defined at the reference level 0.1 rad
        # and scale proportionally, so noise_level -> 0 silences all
        # noise sources.
        scale = self.sim_config.noise_level / 0.1

        for t in range(time_steps):
            # Atmospheric noise (correlated)
            atm_noise = self._generate_correlated_noise(
                (nx, ny),
                self.sim_config.atmospheric_noise * scale,
                correlation_length=20
            )

            # Thermal noise (uncorrelated)
            thermal_noise = self.rng.normal(
                0,
                self.sim_config.thermal_noise * scale,
                (nx, ny)
            )
            
            # Ionospheric noise (time-varying)
            iono_scale = 1 + 0.5 * np.sin(2 * np.pi * t / 24)  # Daily variation
            iono_noise = self.rng.normal(
                0,
                self.sim_config.noise_level * iono_scale,
                (nx, ny)
            )
            
            noisy_phases[t] += atm_noise + thermal_noise + iono_noise
            
        return noisy_phases
        
    def _generate_correlated_noise(self, shape: Tuple[int, int],
                                  amplitude: float,
                                  correlation_length: float) -> np.ndarray:
        """Generate spatially correlated noise"""
        nx, ny = shape
        
        # Generate white noise
        white = self.rng.normal(0, 1, shape)
        
        # Create correlation kernel
        x = np.arange(nx) - nx/2
        y = np.arange(ny) - ny/2
        X, Y = np.meshgrid(x, y, indexing='ij')
        kernel = np.exp(-(X**2 + Y**2) / (2 * correlation_length**2))
        
        # Apply correlation via FFT
        white_fft = np.fft.fft2(white)
        kernel_fft = np.fft.fft2(np.fft.fftshift(kernel))
        correlated = np.fft.ifft2(white_fft * kernel_fft).real
        
        # Normalize
        correlated = amplitude * correlated / np.std(correlated)
        
        return correlated
        

class TelemetryGenerator:
    """Generate telemetry data with realistic characteristics"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.rng = np.random.RandomState(config.seed)
        
    def generate_telemetry(self, phases: np.ndarray,
                          start_time: datetime) -> pd.DataFrame:
        """Generate telemetry time series"""
        time_steps, nx, ny = phases.shape
        
        records = []
        
        for t in range(time_steps):
            timestamp = start_time + timedelta(days=t * self.config.time_interval)
            
            # Sample points (not all pixels in real telemetry)
            sample_rate = 0.1  # 10% of pixels
            mask = self.rng.random((nx, ny)) < sample_rate
            
            sampled_phases = phases[t][mask]
            sampled_x, sampled_y = np.where(mask)

            # Physically-derived attributes (not RNG):
            # - Total phase-noise std from the simulation noise model
            #   (same scaling as ForwardModel.add_noise): coherence is
            #   gamma = exp(-sigma_phi^2 / 2) (standard InSAR relation)
            # - SNR follows from coherence: gamma^2 / (1 - gamma^2)
            # - Incidence angle varies linearly across the swath from
            #   near range (20 deg) to far range (45 deg)
            scale = self.config.noise_level / 0.1
            iono_scale = 1 + 0.5 * np.sin(2 * np.pi * t / 24)
            sigma_phi = np.sqrt(
                (self.config.atmospheric_noise * scale) ** 2
                + (self.config.thermal_noise * scale) ** 2
                + (self.config.noise_level * iono_scale) ** 2
            )
            coherence = float(np.exp(-sigma_phi**2 / 2.0))
            coherence = max(min(coherence, 0.9999), 1e-4)
            snr_linear = coherence**2 / (1.0 - coherence**2)
            snr_db = float(10.0 * np.log10(snr_linear))

            for i, (x, y, phase) in enumerate(zip(sampled_x, sampled_y, sampled_phases)):
                incidence = 20.0 + 25.0 * (y / max(ny - 1, 1))
                # Quality from coherence: good (0) above 0.7, degraded
                # (1) above 0.4, bad (2) below
                if coherence > 0.7:
                    quality = 0
                elif coherence > 0.4:
                    quality = 1
                else:
                    quality = 2
                record = {
                    'timestamp': timestamp,
                    'pixel_x': int(x),
                    'pixel_y': int(y),
                    'phase': float(phase),
                    'coherence': coherence,
                    'snr': snr_db,
                    'satellite_id': self.rng.choice(['SAT1', 'SAT2']),
                    'pass_direction': 'ascending' if t % 2 == 0 else 'descending',
                    'incidence_angle': float(incidence),
                    'quality_flag': quality,
                }
                records.append(record)
                
        return pd.DataFrame(records)
        

class STACMetadataGenerator:
    """Generate STAC-compliant metadata"""
    
    def __init__(self, simulation_id: str):
        self.simulation_id = simulation_id
        
    def generate_collection(self, config: SimulationConfig,
                          anomalies: List[Anomaly]) -> Dict[str, Any]:
        """Generate STAC Collection metadata"""
        return {
            "stac_version": "1.0.0",
            "type": "Collection",
            "id": f"synthetic-ifg-{self.simulation_id}",
            "title": "Synthetic Interferometric Time Series",
            "description": "Simulated interferometric data with procedural subsurface anomalies",
            "license": "CC-BY-4.0",
            "extent": {
                "spatial": {
                    "bbox": [[
                        -180.0, -90.0, 180.0, 90.0  # Global simulation
                    ]]
                },
                "temporal": {
                    "interval": [[
                        datetime.now().isoformat(),
                        (datetime.now() + timedelta(days=config.time_steps)).isoformat()
                    ]]
                }
            },
            "summaries": {
                "instruments": ["synthetic-sar"],
                "platform": ["synthetic-satellite"],
                "processing_level": ["L2"],
                "anomaly_count": len(anomalies),
                "anomaly_types": list(set(a.type for a in anomalies))
            },
            "providers": [{
                "name": "Synthetic Data Generator",
                "roles": ["producer", "processor"],
                "url": "https://example.com"
            }],
            "links": [{
                "rel": "self",
                "href": f"./collection_{self.simulation_id}.json",
                "type": "application/json"
            }]
        }
        
    def generate_item(self, telemetry_path: str,
                     timestamp: datetime,
                     bbox: List[float]) -> Dict[str, Any]:
        """Generate STAC Item metadata"""
        return {
            "stac_version": "1.0.0",
            "type": "Feature",
            "id": f"ifg-{self.simulation_id}-{timestamp.strftime('%Y%m%d')}",
            "collection": f"synthetic-ifg-{self.simulation_id}",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [bbox[0], bbox[1]],
                    [bbox[2], bbox[1]],
                    [bbox[2], bbox[3]],
                    [bbox[0], bbox[3]],
                    [bbox[0], bbox[1]]
                ]]
            },
            "bbox": bbox,
            "properties": {
                "datetime": timestamp.isoformat(),
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
                "platform": "synthetic-satellite",
                "instruments": ["synthetic-sar"],
                "processing_level": "L2",
                "sar:frequency_band": "C",
                "sar:center_frequency": 5.405,
                "sar:polarizations": ["VV"],
                "sar:product_type": "interferogram",
                "view:off_nadir": 30.0,
                "view:incidence_angle": 35.0
            },
            "assets": {
                "data": {
                    "href": telemetry_path,
                    "type": "application/x-parquet",
                    "title": "Telemetry Data",
                    "roles": ["data"]
                }
            },
            "links": [{
                "rel": "self",
                "href": f"./item_{self.simulation_id}.json",
                "type": "application/json"
            }, {
                "rel": "collection",
                "href": f"./collection_{self.simulation_id}.json",
                "type": "application/json"
            }]
        }
        

class SyntheticDataGenerator:
    """Main synthetic data generator orchestrator"""
    
    def __init__(self, sim_config: SimulationConfig = None,
                 sat_config: SatelliteConfig = None):
        self.sim_config = sim_config or SimulationConfig()
        self.sat_config = sat_config or SatelliteConfig()
        self.simulation_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
    def generate(self, output_dir: str = "./data") -> Dict[str, Any]:
        """Generate complete synthetic dataset"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print("Generating synthetic interferometric data...")
        
        # Step 1: Generate subsurface model
        print("  Creating subsurface anomalies...")
        subsurface = SubsurfaceModel(self.sim_config, seed=self.sim_config.seed)
        
        # Add various anomalies. Counts come from the seeded generator
        # (never the global np.random state) so a fixed seed reproduces
        # the exact same dataset.
        count_rng = np.random.RandomState(self.sim_config.seed)
        anomalies = []

        # Add voids
        for _ in range(count_rng.randint(1, 4)):
            anomalies.append(subsurface.add_void())

        # Add tunnels
        for _ in range(count_rng.randint(0, 3)):
            anomalies.append(subsurface.add_tunnel())

        # Add ore bodies
        for _ in range(count_rng.randint(1, 5)):
            anomalies.append(subsurface.add_ore_body())
            
        print(f"  Added {len(anomalies)} anomalies")
        
        # Step 2: Forward model
        print("  Running forward model...")
        forward = ForwardModel(subsurface, self.sat_config, self.sim_config)
        
        g_field = forward.density_to_gravity()
        baselines = forward.gravity_to_baseline(g_field, self.sim_config.time_steps)
        phases = forward.baseline_to_phase(baselines)
        noisy_phases = forward.add_noise(phases)
        
        # Step 3: Generate telemetry
        print("  Generating telemetry data...")
        telemetry_gen = TelemetryGenerator(self.sim_config)
        telemetry = telemetry_gen.generate_telemetry(
            noisy_phases,
            datetime.now()
        )
        
        # Step 4: Save data
        print("  Saving data files...")
        
        # Save telemetry as Parquet
        telemetry_path = output_path / f"telemetry_{self.simulation_id}.parquet"
        telemetry.to_parquet(telemetry_path, engine='pyarrow', compression='snappy')
        
        # Save phase arrays
        phase_path = output_path / f"phases_{self.simulation_id}.npz"
        np.savez_compressed(
            phase_path,
            phases=phases,
            noisy_phases=noisy_phases,
            gravity_field=g_field,
            baselines=baselines,
            density_field=subsurface.density_field
        )
        
        # Step 5: Generate metadata
        print("  Generating STAC metadata...")
        stac_gen = STACMetadataGenerator(self.simulation_id)
        
        # Collection metadata
        collection = stac_gen.generate_collection(self.sim_config, anomalies)
        collection_path = output_path / f"collection_{self.simulation_id}.json"
        with open(collection_path, 'w') as f:
            json.dump(collection, f, indent=2, default=str)
            
        # Item metadata
        item = stac_gen.generate_item(
            str(telemetry_path.name),
            datetime.now(),
            [-180.0, -90.0, 180.0, 90.0]
        )
        item_path = output_path / f"item_{self.simulation_id}.json"
        with open(item_path, 'w') as f:
            json.dump(item, f, indent=2, default=str)
            
        # Dataset card
        dataset_card = self._create_dataset_card(anomalies, telemetry)
        card_path = output_path / f"dataset_card_{self.simulation_id}.json"
        with open(card_path, 'w') as f:
            json.dump(dataset_card, f, indent=2, default=str)
            
        print(f"✓ Synthetic data generated successfully!")
        print(f"  Output directory: {output_path}")
        print(f"  Simulation ID: {self.simulation_id}")
        
        return {
            'simulation_id': self.simulation_id,
            'telemetry_path': str(telemetry_path),
            'phase_path': str(phase_path),
            'collection_path': str(collection_path),
            'item_path': str(item_path),
            'card_path': str(card_path),
            'anomalies': anomalies,
            'telemetry_shape': telemetry.shape,
            'phase_shape': noisy_phases.shape
        }
        
    def _create_dataset_card(self, anomalies: List[Anomaly],
                            telemetry: pd.DataFrame) -> Dict[str, Any]:
        """Create dataset card with metadata"""
        return {
            "name": f"Synthetic Interferometric Dataset {self.simulation_id}",
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "description": "Synthetic interferometric time-series data with procedural subsurface anomalies",
            "configuration": {
                "simulation": asdict(self.sim_config),
                "satellite": asdict(self.sat_config)
            },
            "anomalies": {
                "count": len(anomalies),
                "types": {
                    atype: sum(1 for a in anomalies if a.type == atype)
                    for atype in ['void', 'tunnel', 'ore']
                }
            },
            "statistics": {
                "telemetry": {
                    "num_records": len(telemetry),
                    "time_range": [
                        telemetry['timestamp'].min().isoformat(),
                        telemetry['timestamp'].max().isoformat()
                    ],
                    "phase_range": [
                        float(telemetry['phase'].min()),
                        float(telemetry['phase'].max())
                    ],
                    "mean_coherence": float(telemetry['coherence'].mean()),
                    "mean_snr": float(telemetry['snr'].mean())
                }
            },
            "schema": {
                "telemetry": list(telemetry.columns),
                "phase_data": ["phases", "noisy_phases", "gravity_field", "baselines", "density_field"]
            }
        }


# Example usage
if __name__ == "__main__":
    # Configure simulation
    sim_config = SimulationConfig(
        grid_size=(100, 100, 50),
        time_steps=100,
        seed=42,
        noise_level=0.1
    )
    
    sat_config = SatelliteConfig(
        num_satellites=2,
        orbital_height=500e3,
        baseline_nominal=200.0
    )
    
    # Generate synthetic data
    generator = SyntheticDataGenerator(sim_config, sat_config)
    results = generator.generate()
    
    print(f"\nGenerated files:")
    for key, value in results.items():
        if 'path' in key:
            print(f"  {key}: {value}")
