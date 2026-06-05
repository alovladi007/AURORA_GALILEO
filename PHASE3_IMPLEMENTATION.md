# GALILEO V2.0 — Phase 3 Implementation

Phase 3 implements **Real-Time Data Pipeline** with WebSocket streaming from Kafka
topics and begins **Frontend Integration** to replace mock data with real API calls.

## Summary

| Component | Before | After |
|-----------|--------|-------|
| **API Gateway** | REST-only HTTP endpoints | WebSocket bridge `/ws/stream`, `/ws/telemetry`, `/ws/gravity` streaming live Kafka→client; dedicated endpoints with satellite filtering |
| **Frontend (UI)** | Mock data hooks, no real-time streams | New `useRealTimeStream` hooks for live telemetry/gravity; WebSocket integration ready for dashboard |

## New Modules

### API Gateway (`services/api-gateway/src/api/`)

- **`websocket_bridge.py`** (~230 lines)
  - `WebSocketBridge`: Kafka consumer → WebSocket broadcaster
  - `WebSocketClient`: per-client subscription state, message queue (max 100), backpressure handling
  - In-process fallback when Kafka unavailable (publishes to `asyncio.Queue`)
  - Subscription filtering: topics (`galileo.telemetry`, `galileo.gravity`) + satellite IDs
  - Graceful degradation: no Kafka → in-process streaming only
  ```python
  class WebSocketClient:
      def __init__(self, websocket: WebSocket, client_id: str):
          self.websocket = websocket
          self.subscriptions: Set[str] = set()
          self.satellite_filters: Set[str] = set()
          self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
          
      async def send(self, message: Dict[str, Any]):
          try:
              self.message_queue.put_nowait(message)
          except asyncio.QueueFull:
              logger.warning(f"Client {self.client_id} queue full, dropping message")
  
  class WebSocketBridge:
      async def _consume_kafka(self, topic: str):
          consumer = KafkaConsumer(
              topic, bootstrap_servers=self.kafka_servers,
              value_deserializer=lambda m: json.loads(m.decode('utf-8')),
              auto_offset_reset='latest',
              group_id=f'websocket_bridge_{topic}',
          )
          while self.running:
              msg_pack = consumer.poll(timeout_ms=1000)
              for tp, messages in msg_pack.items():
                  for message in messages:
                      await self._broadcast(topic, message.value)
  ```

- **`websocket_routes.py`** (~150 lines)
  - `/ws/stream`: main endpoint with dynamic subscription (client sends `{"action": "subscribe", "topics": [...], "satellite_ids": [...]}`)
  - `/ws/telemetry?satellite_id=SAT001`: dedicated auto-subscribed telemetry stream
  - `/ws/gravity?satellite_id=SAT001`: dedicated auto-subscribed gravity stream
  - Protocol:
    - Client → Server: `{action: "subscribe"/"unsubscribe", topics: [...], satellite_ids: [...]}`
    - Server → Client: `{type: "data"/"subscription_confirmed"/"ping"/"error", topic: "galileo.telemetry", data: {...}}`

### API Gateway Updates

- **`main.py`**:
  - Added WebSocket router inclusion: `app.include_router(websocket_router)`
  - Lifespan startup: `bridge = get_bridge(); await bridge.start()`
  - Lifespan shutdown: `await bridge.stop()`

- **`requirements.txt`**:
  - Added `websockets==12.0`, `kafka-python==2.0.2`

### Frontend (UI) (`ui/src/hooks/`)

- **`useRealTimeStream.ts`** (~340 lines)
  - `useRealTimeStream()`: main hook for multi-topic subscription with satellite filtering
    - Returns `{status, subscribedTopics, telemetryData, gravityData, subscribe, unsubscribe, clearData}`
    - Automatically reconnects (max 5 attempts, 3s interval)
    - Keeps last 100 messages per topic
  - `useTelemetryStream(satelliteIds?)`: dedicated telemetry hook
    - Auto-connects to `/ws/telemetry?satellite_id=...`
    - Returns `{status, latestTelemetry: Map<sat_id, data>, telemetryHistory}`
  - `useGravityStream(satelliteIds?)`: dedicated gravity hook
    - Auto-connects to `/ws/gravity?satellite_id=...`
    - Returns `{status, latestGravity: Map<sat_id, data>, gravityHistory}`
  ```typescript
  export function useRealTimeStream(options: UseRealTimeStreamOptions = {}) {
    const [status, setStatus] = useState<StreamStatus>('disconnected')
    const [subscribedTopics, setSubscribedTopics] = useState<string[]>([])
    const [telemetryData, setTelemetryData] = useState<TelemetryData[]>([])
    
    const subscribe = useCallback((topics: string[], satellites?: string[]) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          action: 'subscribe',
          topics,
          satellite_ids: satellites || satelliteFilter,
        }))
        return true
      }
      return false
    }, [satelliteFilter])
    
    return {
      status, connected: status === 'connected',
      subscribedTopics, telemetryData, gravityData,
      subscribe, unsubscribe, clearData,
    }
  }
  ```

### Testing

- **`services/api-gateway/tests/test_websocket_client.py`** (~170 lines)
  - Three test scenarios:
    1. `/ws/stream` with dynamic subscription (30s listen)
    2. `/ws/telemetry?satellite_id=SAT001` (15s listen, filtered)
    3. `/ws/gravity` (15s listen, all satellites)
  - Prints received messages with timestamps, satellite IDs, values

## Verified Results

- **WebSocket Bridge**: Graceful degradation verified — bridge starts with or without Kafka
- **In-Process Fallback**: Data Service publishes to Kafka + in-process queue; WebSocket bridge consumes from in-process queue when Kafka unavailable
- **Subscription Filtering**: Client can subscribe to specific topics and filter by satellite IDs
- **Backpressure**: Client queue maxsize=100; drops messages when full (logged warning)
- **Frontend Hooks**: TypeScript hooks ready for integration in dashboards; provide Map of latest values per satellite + rolling history (last 100/200 records)

## Protocol Example

Client connects to `/ws/stream`:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/stream')

// Server sends welcome
{"type": "connected", "available_topics": ["galileo.telemetry", "galileo.gravity"]}

// Client subscribes
ws.send(JSON.stringify({
  action: "subscribe",
  topics: ["galileo.telemetry", "galileo.gravity"],
  satellite_ids: ["SAT001", "SAT002"]
}))

// Server confirms
{"type": "subscription_confirmed", "topics": ["galileo.telemetry", "galileo.gravity"], "satellite_ids": ["SAT001", "SAT002"]}

// Server streams data
{"type": "data", "topic": "galileo.telemetry", "timestamp": "2024-01-15T12:00:00Z", "data": {...}}
{"type": "data", "topic": "galileo.gravity", "timestamp": "2024-01-15T12:00:01Z", "data": {...}}
```

## Event-Driven Workflows (Week 14)

### API Gateway (`services/api-gateway/src/api/`)

- **`event_orchestrator.py`** (~370 lines)
  - `EventOrchestrator`: Subscribes to Kafka event topics, executes cross-service workflows
  - `Workflow`: Declarative workflow definitions with steps, conditions, retry logic
  - `WorkflowExecution`: Tracks running workflows (status, completed/failed steps, errors)
  - Built-in workflows:
    1. **auto_ml_retrain**: `data_ingested` → check volume → trigger ML training
    2. **update_mission_after_inversion**: `inversion_completed` → get result → create mission plan
    3. **refresh_inversion_after_maneuver**: `maneuver_executed` → query telemetry → start inversion
  - Execution: async with retries (exponential backoff), per-step gRPC calls
  - Topics: `galileo.events.data`, `galileo.events.ml`, `galileo.events.inversion`, `galileo.events.control`

- **`workflow_routes.py`** (~150 lines)
  - `/api/v1/workflows/executions`: list all workflow executions (filtered by status)
  - `/api/v1/workflows/executions/{id}`: get execution details
  - `/api/v1/workflows/trigger`: manually trigger workflow by publishing event
  - `/api/v1/workflows/workflows`: list all registered workflows
  - `/api/v1/workflows/statistics`: execution stats (total, completed, failed, success rate)

### API Gateway Updates

- **`main.py`**:
  - Lifespan: `orchestrator = get_orchestrator(); orchestrator.register_grpc_stubs(grpc_manager.stubs); await orchestrator.start()`
  - Added workflow router

## gRPC Server-Side Streaming (Week 14)

### Data Service (`services/data-service/src/service.py`)

- **`StreamTelemetry(QueryTelemetryRequest) returns (stream SatelliteTelemetry)`**
  - Real-time telemetry stream from in-process broker (Kafka fallback)
  - Filters by `satellite_ids` from request
  - Yields records as they arrive, respects context cancellation
  - Client disconnect → stops stream gracefully

- **`StreamGravity(QueryGravityRequest) returns (stream GravityMeasurement)`**
  - Real-time gravity measurement stream
  - Filters by `satellite_ids` AND bounding box (`min/max_latitude/longitude`)
  - Yields filtered records, handles context cancellation

Both use `broker.stream(topic, stop_event)` which yields live records from in-process queues (Kafka topic if available).

## Next Steps (Phase 3 Continuation — Weeks 13-14)

**Weeks 11-12: Complete** (WebSocket bridge + frontend hooks + event workflows + gRPC streaming)  
**Weeks 13-14: In Progress**

### Frontend Dashboard Integration (Week 13)
- **Replace mock data in components**:
  - `GlobeViewer.tsx`: use `useTelemetryStream()` for live satellite positions
  - `DataPanel.tsx`: use `useGravityStream()` for real-time gravity field updates
  - `MissionDashboard.tsx`: integrate WebSocket status indicators
  - `JobConsole.tsx`: connect to job status updates via existing backend or WebSocket extension

### 3D Visualization (Week 13)
- **Real-time satellite overlay** on Cesium globe (already in UI; wire to WebSocket)
- **Gravity field heatmap** from `useGravityStream()` data
- **Orbit traces**: store telemetry history, render as polyline on globe

### Event-Driven Workflows (Week 14)
- **Cross-service events** via Kafka:
  - `data_ingested` → trigger ML retraining workflow
  - `inversion_completed` → notify Control Service for mission re-planning
  - `maneuver_executed` → update inversion data query bounds
- **Workflow orchestrator** in API Gateway or separate service:
  - Subscribe to event topics
  - Dispatch gRPC calls to downstream services
  - Track workflow state (pending/completed/failed)

### gRPC Server-Side Streaming (Week 14)
- **Data Service**: `StreamTelemetry`, `StreamGravity` RPCs (already prototyped in `streaming.py` broker)
- **Inversion Service**: `StreamInversionProgress` for live iteration updates
- **Control Service**: `StreamSimulationProgress` for async mission simulation
- **API Gateway**: expose gRPC streams as WebSocket endpoints (bridge gRPC stream → WebSocket)

## Files Created/Modified

**New Files:**
- `services/api-gateway/src/api/websocket_bridge.py`
- `services/api-gateway/src/api/websocket_routes.py`
- `services/api-gateway/src/api/event_orchestrator.py`
- `services/api-gateway/src/api/workflow_routes.py`
- `services/api-gateway/tests/test_websocket_client.py`
- `ui/src/hooks/useRealTimeStream.ts`
- `ui/src/components/LiveSatelliteTracker.tsx`

**Modified Files:**
- `services/api-gateway/src/main.py` (WebSocket router, workflow router, bridge + orchestrator startup/shutdown)
- `services/api-gateway/requirements.txt` (websockets, kafka-python)
- `services/data-service/src/service.py` (StreamTelemetry, StreamGravity RPCs)

## Impact

- **Real-Time Capability**: Platform now supports live telemetry/gravity streaming from ingest to frontend
- **Scalability**: Kafka decouples producers (Data Service) from consumers (API Gateway, analytics)
- **Event-Driven Architecture**: Cross-service workflows triggered by events (data ingestion, job completion, maneuvers)
- **gRPC Streaming**: Low-latency server-side streaming for real-time data feeds
- **Developer Experience**: Frontend developers can use clean hooks without managing WebSocket protocol; backend developers define workflows declaratively
- **Graceful Degradation**: Full stack runs without Kafka (in-process fallback), suitable for local dev and testing
- **Observability**: Workflow execution tracking, statistics, manual triggering via REST API

## Follow-Ups (Phase 4+)

- **Production Hardening** (Phase 4): distributed tracing through WebSocket connections, metrics (active connections, messages/sec), circuit breakers for Kafka consumer
- **Advanced Features** (Phase 5): WebSocket compression, binary protocol (MessagePack/protobuf), multi-region Kafka replication

---

**Phase 3 Status**: **Weeks 11-14 Core Features Complete**
- ✅ WebSocket bridge (Kafka→WebSocket, subscription filtering, backpressure)
- ✅ Frontend real-time hooks (useRealTimeStream, useTelemetryStream, useGravityStream)
- ✅ LiveSatelliteTracker component (3D visualization with real-time streams)
- ✅ Event-driven workflows (auto ML retraining, mission re-planning, inversion refresh)
- ✅ Workflow orchestration API (execution tracking, statistics, manual triggers)
- ✅ gRPC server-side streaming (StreamTelemetry, StreamGravity)

**Remaining Week 13-14 Tasks**:
- Dashboard integration (wire existing components to real-time streams)
- 3D visualization polish (gravity heatmap rendering, orbit trail smoothing)
- Workflow integration tests
