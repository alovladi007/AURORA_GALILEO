# Geophysics Module - Quick Reference Guide

## Common Tasks

### 1. Compute Gravity Anomaly

```python
from geophysics import load_egm96, compute_gravity_anomaly
import numpy as np

# Load gravity model
egm96 = load_egm96()

# Your observation data
lat = np.array([40.0, 41.0, 42.0])
lon = np.array([-120.0, -119.0, -118.0])
observed_g = np.array([980200, 980150, 980180])  # mGal
elevation = np.array([100, 200, 150])  # meters

# Compute free-air anomaly
anomaly, components = compute_gravity_anomaly(
    lat, lon, observed_g, egm96,
    correction_type='free_air',
    elevation=elevation
)

print(f"Free-air anomaly: {anomaly} mGal")
```

### 2. Apply Terrain Correction

```python
from geophysics import load_crust1, terrain_correction
import numpy as np

# Load crustal model
crust = load_crust1()

# Station data
lat = np.array([40.0])
lon = np.array([-120.0])
elevation = np.array([500.0])

# DEM data (simplified example)
dem = np.random.rand(100, 100) * 1000
dem_lat = np.linspace(39, 41, 100)
dem_lon = np.linspace(-121, -119, 100)

# Compute terrain correction
corr = terrain_correction(
    lat, lon, elevation,
    dem, dem_lat, dem_lon,
    density=2670.0,
    radius=50000.0  # 50 km
)

print(f"Terrain correction: {corr[0]:.4f} mGal")
```

### 3. Seasonal Water Correction

```python
from geophysics import load_seasonal_water, hydrological_correction
from datetime import datetime

# Load seasonal water model
hydro = load_seasonal_water(source='GLDAS')

# Observation data
lat = np.array([40.0])
lon = np.array([-120.0])
obs_time = datetime(2024, 6, 15)
ref_time = datetime(2024, 1, 15)

# Compute correction
corr = hydrological_correction(lat, lon, obs_time, hydro, ref_time)

print(f"Hydrological correction: {corr[0]:.4f} mGal")
```

### 4. Ocean/Land Masking

```python
from geophysics import load_ocean_mask

# Load global mask
mask = load_ocean_mask(resolution=1.0)

# Check if points are on land
lat = np.array([40.0, 0.0])  # California, Pacific
lon = np.array([-120.0, -150.0])

is_land = mask.is_land(lat, lon)
is_ocean = mask.is_ocean(lat, lon)

print(f"Land: {is_land}")
print(f"Ocean: {is_ocean}")
```

### 5. Complete Bouguer Anomaly

```python
from geophysics import complete_bouguer_anomaly

# All your data
lat = np.array([40.0, 41.0])
lon = np.array([-120.0, -119.0])
observed_g = np.array([980200, 980150])
elevation = np.array([100, 200])

# DEM
dem = np.random.rand(100, 100) * 1000
dem_lat = np.linspace(39, 42, 100)
dem_lon = np.linspace(-121, -118, 100)

# Compute complete Bouguer anomaly
result = complete_bouguer_anomaly(
    lat, lon, observed_g, elevation,
    dem, dem_lat, dem_lon,
    density=2670.0
)

print(f"Complete Bouguer Anomaly: {result['complete_bouguer_anomaly']}")
print(f"Free-air anomaly: {result['free_air_anomaly']}")
print(f"Simple Bouguer: {result['simple_bouguer_anomaly']}")
```

### 6. Joint Inversion Setup

```python
from geophysics import setup_joint_inversion, integrate_gravity_seismic, perform_joint_inversion

# Setup with gravity data
lat = np.array([40.0, 41.0])
lon = np.array([-120.0, -119.0])
gravity = np.array([980200, 980150])

joint_model = setup_joint_inversion(gravity, lat, lon)

# Add seismic data
velocity = np.array([5000, 5500])  # m/s
joint_model = integrate_gravity_seismic(
    joint_model, velocity,
    seismic_type='velocity',
    coupling_type='petrophysical'
)

# Run inversion
results = perform_joint_inversion(joint_model, max_iterations=50)

print(f"RMS error: {results['rms_error']:.4f} mGal")
print(f"Converged: {results['converged']}")
```

## Data Format Requirements

### Coordinates
- **Format**: WGS84 decimal degrees
- **Latitude**: -90 to 90
- **Longitude**: -180 to 180

### Gravity
- **Units**: mGal (10⁻⁵ m/s²)
- **Typical range**: 978000 to 983000 mGal

### Elevation
- **Units**: meters above ellipsoid
- **Typical range**: -500 to 8000 m

### Density
- **Units**: kg/m³
- **Typical crustal**: 2670 kg/m³
- **Typical mantle**: 3300 kg/m³

### Water Storage
- **Units**: mm water equivalent
- **Typical seasonal**: ±100 mm

## Common Corrections Summary

| Correction | Typical Magnitude | Formula |
|------------|------------------|---------|
| Free-air | 0.3086 mGal/m × h | -0.3086·h |
| Bouguer | 0.1119 mGal/m × h | 0.1119·ρ·h |
| Terrain | 0-10 mGal | Complex |
| Hydrology | 0-0.1 mGal | 0.042 µGal/mm |

## Error Handling

```python
try:
    anomaly, components = compute_gravity_anomaly(
        lat, lon, observed_g, egm96,
        correction_type='free_air',
        elevation=elevation
    )
except ValueError as e:
    print(f"Error in gravity computation: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Performance Tips

### For Large Datasets

```python
# Process in batches
batch_size = 1000
for i in range(0, len(lat), batch_size):
    batch_lat = lat[i:i+batch_size]
    batch_lon = lon[i:i+batch_size]
    batch_g = observed_g[i:i+batch_size]
    
    anomaly_batch = compute_gravity_anomaly(
        batch_lat, batch_lon, batch_g, egm96
    )
```

### Memory Management

```python
# Use memory-mapped arrays for large DEMs
import numpy as np
dem = np.memmap('dem.dat', dtype='float32', 
                mode='r', shape=(10000, 10000))
```

## Validation Checklist

✓ Check coordinate ranges (-90≤lat≤90, -180≤lon≤180)  
✓ Verify gravity values are in mGal (~980000)  
✓ Ensure elevation is in meters  
✓ Confirm density values are reasonable (2000-3500 kg/m³)  
✓ Check for NaN or infinite values  
✓ Validate array shapes match  

## Troubleshooting

### Common Issues

**Issue**: Import errors  
**Solution**: Ensure `/home/claude` is in Python path

**Issue**: NaN values in output  
**Solution**: Check for invalid coordinates or missing data

**Issue**: Slow terrain correction  
**Solution**: Reduce radius or use coarser DEM

**Issue**: Shape mismatch errors  
**Solution**: Ensure all arrays have compatible shapes

## Further Reading

- Full Documentation: `/home/claude/docs/earth_models.md`
- Examples: `/home/claude/examples/complete_geophysics_example.py`
- Tests: `/home/claude/test_geophysics.py`
- Benchmarks: `/home/claude/benchmarks/background_removal_benchmarks.py`

## Support

For questions or issues:
1. Check the full documentation
2. Review example scripts
3. Run the test suite: `python test_geophysics.py`

---

**Quick Start Command**

```bash
python -c "from geophysics import *; print('Geophysics module ready!')"
```

**Verify Installation**

```bash
python /home/claude/test_geophysics.py
```

Expected output: `6/6 tests passed`
