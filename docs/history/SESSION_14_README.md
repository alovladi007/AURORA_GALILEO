# Optical Bench Emulator

A comprehensive software emulation system for short-baseline optical interferometers.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the complete system (recommended)
python start_emulator.py
```

The dashboard will open automatically at `http://localhost:8080/dashboard.html`

## What's Included

### Core Components
- `optical_bench.py` - Emulator engine with realistic signal generation
- `server.py` - WebSocket server for real-time data streaming  
- `dashboard.html` - Interactive web-based visualization dashboard
- `dashboard_server.py` - HTTP server for the dashboard

### Demo Scripts
- `demo_basic.py` - Basic operation and data capture
- `demo_events.py` - Event injection scenarios
- `demo_streaming.py` - Continuous data streaming examples

### Utilities
- `start_emulator.py` - Master startup script
- `requirements.txt` - Python dependencies
- `__init__.py` - Package initialization

## Manual Start

If you prefer to start components separately:

```bash
# Terminal 1: WebSocket server
python server.py

# Terminal 2: Dashboard server
python dashboard_server.py

# Terminal 3: Run demos
python demo_basic.py
python demo_events.py
python demo_streaming.py
```

## System Architecture

```
Optical Bench Emulator Core
         ↓
WebSocket Server (ws://localhost:8765)
         ↓
Dashboard (http://localhost:8080/dashboard.html)
```

## Key Features

### Realistic Signal Generation
- Interference patterns with 95% visibility
- Thermal drift and expansion effects  
- Multi-mode vibration (50 Hz mains, 120 Hz pumps, 17 Hz building)
- Laser intensity fluctuations
- Spatial fringe patterns

### Event Injection
- Vibration spikes
- Thermal jumps
- Laser dropouts  
- Phase steps

### Real-Time Monitoring
- 50 Hz default update rate (configurable)
- Live plots and metrics
- System diagnostics
- Event logging

## Documentation

Full documentation available in: `/docs/emulation.md`

Topics covered:
- System architecture
- Installation and setup
- API reference
- WebSocket protocol
- Advanced usage examples
- Troubleshooting

## Requirements

- Python 3.8+
- numpy >= 1.24.0
- websockets >= 11.0
- Modern web browser (Chrome, Firefox, Safari, Edge)

## Typical Use Cases

1. **Testing Data Acquisition Systems**
   ```python
   from optical_bench import OpticalBenchEmulator
   
   emulator = OpticalBenchEmulator()
   state = emulator.get_full_state()
   ```

2. **Real-Time Visualization**
   - Start system with `python start_emulator.py`
   - View dashboard in browser
   - Monitor live signals and inject events

3. **Algorithm Development**
   - Generate synthetic datasets
   - Test signal processing algorithms
   - Validate analysis pipelines

4. **Demonstration and Training**
   - Show interferometer behavior
   - Demonstrate environmental effects
   - Train operators on system responses

## Quick Reference

### Inject Events via Dashboard
- Click "Inject Vibration Spike" for mechanical disturbance
- Click "Thermal Jump" for temperature change
- Click "Laser Dropout" for intensity fluctuation
- Click "Phase Step" for optical path change
- Click "Reset Emulator" to return to initial state

### Inject Events via Code
```python
emulator.inject_event("vibration_spike", 10.0)
emulator.inject_event("thermal_jump", 0.5)
emulator.inject_event("laser_dropout", 3.0)
emulator.inject_event("phase_step", 100)
```

### Get Current State
```python
state = emulator.get_full_state()
intensity = state['interference']['intensity']
phase = state['interference']['phase']
temperature = state['thermal']['temperature']
```

### System Diagnostics
```python
diag = emulator.get_diagnostics()
print(f"Stability: {diag['stability_score']:.2f}")
print(f"Data Quality: {diag['data_quality']}")
```

## File Structure

```
emulator/
├── __init__.py              # Package initialization
├── optical_bench.py         # Core emulator engine
├── server.py                # WebSocket server
├── dashboard.html           # Web dashboard
├── dashboard_server.py      # HTTP server
├── start_emulator.py        # Master startup script
├── demo_basic.py            # Basic demo
├── demo_events.py           # Event injection demo
├── demo_streaming.py        # Streaming demo
├── requirements.txt         # Dependencies
└── README.md                # This file

docs/
└── emulation.md             # Full documentation
```

## Support

For detailed information, refer to the full documentation in `/docs/emulation.md`.

For issues or questions:
1. Check the troubleshooting section in the documentation
2. Review the demo scripts for usage examples
3. Examine the API reference for detailed method descriptions

## Version

Current version: 1.0.0

---

**Ready to emulate!** 🔬
