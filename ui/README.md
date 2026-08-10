# GALILEO Platform - Web UI

Modern Next.js web application with CesiumJS 3D globe visualization, connecting to microservices backend.

## Quick Start

```bash
# Install dependencies
npm install

# Set up environment variables
cp .env.local.example .env.local
# Edit .env.local and configure:
# - NEXT_PUBLIC_API_URL=http://localhost:28000 (API Gateway)
# - NEXT_PUBLIC_CESIUM_ION_TOKEN=your_token_here

# Run development server
npm run dev
```

Visit http://localhost:13003 (alternative port to avoid conflicts)

## Architecture

The UI connects to GALILEO's microservices through the API Gateway:

```
UI (Next.js) → API Gateway (port 28000) → Microservices (gRPC)
                                          ├─ Data Service
                                          ├─ ML Service
                                          ├─ Inversion Service
                                          └─ Control Service
```

## Features

- **3D Globe Viewer**: CesiumJS-powered Earth visualization
- **Real-time Telemetry**: Live satellite data streaming
- **Orbit Visualization**: Real-time satellite orbit rendering
- **Gravity Mapping**: Geophysical gravity anomaly visualization
- **ML Model Management**: Train, deploy, and monitor models
- **Inversion Jobs**: Start and track gravity field inversions
- **Satellite Control**: Send commands and monitor satellites
- **API Integration**: Connects to microservices via API Gateway (port 28000)

## Get Cesium Ion Token

1. Visit https://ion.cesium.com/
2. Sign up for a free account
3. Go to Access Tokens
4. Copy your default token
5. Add to `.env.local`:
   ```
   NEXT_PUBLIC_CESIUM_ION_TOKEN=your_token_here
   ```

## Build for Production

```bash
npm run build
npm start
```

## Tech Stack

- **Next.js 14**: React framework
- **TypeScript**: Type safety
- **TailwindCSS**: Styling
- **CesiumJS**: 3D globe visualization
- **Resium**: React components for Cesium
