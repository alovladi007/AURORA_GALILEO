/**
 * Real-Time Data Stream Hook
 *
 * Connects to the API Gateway WebSocket endpoints for live telemetry and
 * gravity data streaming. Uses the galileo.telemetry and galileo.gravity
 * Kafka topics bridged to WebSocket.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

const WS_GATEWAY_URL = process.env.NEXT_PUBLIC_WS_GATEWAY_URL || 'ws://localhost:8000'

export type StreamStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface TelemetryData {
  satellite_id: string
  timestamp: string
  location: {
    latitude: number
    longitude: number
    altitude: number
  }
  temperature: number
  battery_level: number
}

export interface GravityData {
  satellite_id: string
  timestamp: string
  measurement_id: string
  gravity_value: number
  uncertainty: number
  quality_flag: string
  location: {
    latitude: number
    longitude: number
    altitude: number
  }
}

export interface StreamMessage {
  type: 'data' | 'subscription_confirmed' | 'ping' | 'pong' | 'error' | 'connected'
  topic?: string
  timestamp?: string
  data?: TelemetryData | GravityData | any
  message?: string
  available_topics?: string[]
  topics?: string[]
  satellite_ids?: string[]
}

interface UseRealTimeStreamOptions {
  autoConnect?: boolean
  reconnect?: boolean
  reconnectInterval?: number
  maxReconnectAttempts?: number
  satelliteFilter?: string[]
  onTelemetry?: (data: TelemetryData) => void
  onGravity?: (data: GravityData) => void
  onError?: (error: string) => void
}

/**
 * Main stream hook - connects to /ws/stream and allows subscription to multiple topics
 */
export function useRealTimeStream(options: UseRealTimeStreamOptions = {}) {
  const {
    autoConnect = true,
    reconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    satelliteFilter = [],
    onTelemetry,
    onGravity,
    onError,
  } = options

  const [status, setStatus] = useState<StreamStatus>('disconnected')
  const [subscribedTopics, setSubscribedTopics] = useState<string[]>([])
  const [telemetryData, setTelemetryData] = useState<TelemetryData[]>([])
  const [gravityData, setGravityData] = useState<GravityData[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      const url = `${WS_GATEWAY_URL}/ws/stream`
      setStatus('connecting')

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        reconnectAttemptsRef.current = 0
        console.log('WebSocket connected to API Gateway')
      }

      ws.onmessage = (event) => {
        try {
          const message: StreamMessage = JSON.parse(event.data)

          switch (message.type) {
            case 'connected':
              console.log('Stream ready:', message.available_topics)
              break

            case 'subscription_confirmed':
              setSubscribedTopics(message.topics || [])
              console.log('Subscribed to:', message.topics)
              break

            case 'data':
              if (message.topic === 'galileo.telemetry' && message.data) {
                const telem = message.data as TelemetryData
                setTelemetryData((prev) => [...prev.slice(-99), telem])
                onTelemetry?.(telem)
              } else if (message.topic === 'galileo.gravity' && message.data) {
                const grav = message.data as GravityData
                setGravityData((prev) => [...prev.slice(-99), grav])
                onGravity?.(grav)
              }
              break

            case 'ping':
              ws.send(JSON.stringify({ type: 'pong' }))
              break

            case 'error':
              console.error('Stream error:', message.message)
              onError?.(message.message || 'Unknown error')
              break
          }
        } catch (e) {
          console.error('Failed to parse stream message:', e)
        }
      }

      ws.onclose = () => {
        setStatus('disconnected')
        wsRef.current = null

        if (reconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++
          console.log(`Reconnecting (attempt ${reconnectAttemptsRef.current})...`)
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, reconnectInterval)
        }
      }

      ws.onerror = (error) => {
        setStatus('error')
        console.error('WebSocket error:', error)
      }
    } catch (error) {
      setStatus('error')
      console.error('WebSocket connection error:', error)
    }
  }, [reconnect, reconnectInterval, maxReconnectAttempts, onTelemetry, onGravity, onError])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    reconnectAttemptsRef.current = maxReconnectAttempts

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setStatus('disconnected')
  }, [maxReconnectAttempts])

  const subscribe = useCallback((topics: string[], satellites?: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'subscribe',
        topics,
        satellite_ids: satellites || satelliteFilter,
      }))
      return true
    }
    console.warn('WebSocket not connected, cannot subscribe')
    return false
  }, [satelliteFilter])

  const unsubscribe = useCallback((topics: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'unsubscribe',
        topics,
      }))
      return true
    }
    return false
  }, [])

  const clearData = useCallback(() => {
    setTelemetryData([])
    setGravityData([])
  }, [])

  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [autoConnect, connect, disconnect])

  return {
    status,
    connected: status === 'connected',
    subscribedTopics,
    telemetryData,
    gravityData,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    clearData,
  }
}

/**
 * Dedicated telemetry stream hook - auto-subscribes to galileo.telemetry
 */
export function useTelemetryStream(satelliteIds?: string[]) {
  const [latestTelemetry, setLatestTelemetry] = useState<Map<string, TelemetryData>>(new Map())
  const [telemetryHistory, setTelemetryHistory] = useState<TelemetryData[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<StreamStatus>('disconnected')

  useEffect(() => {
    const url = satelliteIds && satelliteIds.length > 0
      ? `${WS_GATEWAY_URL}/ws/telemetry?satellite_id=${satelliteIds[0]}`
      : `${WS_GATEWAY_URL}/ws/telemetry`

    setStatus('connecting')
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      console.log('Telemetry stream connected')
    }

    ws.onmessage = (event) => {
      try {
        const message: StreamMessage = JSON.parse(event.data)

        if (message.type === 'data' && message.data) {
          const telem = message.data as TelemetryData
          setLatestTelemetry((prev) => {
            const next = new Map(prev)
            next.set(telem.satellite_id, telem)
            return next
          })
          setTelemetryHistory((prev) => [...prev.slice(-199), telem])
        } else if (message.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }))
        }
      } catch (e) {
        console.error('Failed to parse telemetry message:', e)
      }
    }

    ws.onclose = () => {
      setStatus('disconnected')
    }

    ws.onerror = () => {
      setStatus('error')
    }

    return () => {
      ws.close()
    }
  }, [satelliteIds])

  return {
    status,
    connected: status === 'connected',
    latestTelemetry,
    telemetryHistory,
    clearHistory: () => setTelemetryHistory([]),
  }
}

/**
 * Dedicated gravity stream hook - auto-subscribes to galileo.gravity
 */
export function useGravityStream(satelliteIds?: string[]) {
  const [latestGravity, setLatestGravity] = useState<Map<string, GravityData>>(new Map())
  const [gravityHistory, setGravityHistory] = useState<GravityData[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<StreamStatus>('disconnected')

  useEffect(() => {
    const url = satelliteIds && satelliteIds.length > 0
      ? `${WS_GATEWAY_URL}/ws/gravity?satellite_id=${satelliteIds[0]}`
      : `${WS_GATEWAY_URL}/ws/gravity`

    setStatus('connecting')
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      console.log('Gravity stream connected')
    }

    ws.onmessage = (event) => {
      try {
        const message: StreamMessage = JSON.parse(event.data)

        if (message.type === 'data' && message.data) {
          const grav = message.data as GravityData
          setLatestGravity((prev) => {
            const next = new Map(prev)
            next.set(grav.satellite_id, grav)
            return next
          })
          setGravityHistory((prev) => [...prev.slice(-199), grav])
        } else if (message.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }))
        }
      } catch (e) {
        console.error('Failed to parse gravity message:', e)
      }
    }

    ws.onclose = () => {
      setStatus('disconnected')
    }

    ws.onerror = () => {
      setStatus('error')
    }

    return () => {
      ws.close()
    }
  }, [satelliteIds])

  return {
    status,
    connected: status === 'connected',
    latestGravity,
    gravityHistory,
    clearHistory: () => setGravityHistory([]),
  }
}

export default useRealTimeStream
