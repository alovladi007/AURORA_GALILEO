/**
 * WebSocket Client Hook
 *
 * Provides real-time communication with the backend for:
 * - Task status updates
 * - Emulator signal streaming
 * - Simulation progress
 */

import { useCallback, useEffect, useRef, useState } from 'react'

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:5050'

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface WebSocketMessage {
  type: string
  data?: any
  timestamp?: string
  task_id?: string
  emulator_id?: string
  message?: string
}

interface UseWebSocketOptions {
  autoConnect?: boolean
  reconnect?: boolean
  reconnectInterval?: number
  maxReconnectAttempts?: number
  onMessage?: (message: WebSocketMessage) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
}

export function useWebSocket(
  endpoint: string,
  options: UseWebSocketOptions = {}
) {
  const {
    autoConnect = true,
    reconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    onMessage,
    onOpen,
    onClose,
    onError,
  } = options

  const [status, setStatus] = useState<WebSocketStatus>('disconnected')
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)
  const [messages, setMessages] = useState<WebSocketMessage[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      const url = `${WS_BASE_URL}${endpoint}`
      setStatus('connecting')

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        reconnectAttemptsRef.current = 0
        onOpen?.()
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage
          setLastMessage(message)
          setMessages((prev) => [...prev.slice(-99), message]) // Keep last 100 messages
          onMessage?.(message)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onclose = () => {
        setStatus('disconnected')
        wsRef.current = null
        onClose?.()

        // Attempt reconnection
        if (reconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, reconnectInterval)
        }
      }

      ws.onerror = (error) => {
        setStatus('error')
        onError?.(error)
      }
    } catch (error) {
      setStatus('error')
      console.error('WebSocket connection error:', error)
    }
  }, [endpoint, reconnect, reconnectInterval, maxReconnectAttempts, onMessage, onOpen, onClose, onError])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    reconnectAttemptsRef.current = maxReconnectAttempts // Prevent reconnection

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setStatus('disconnected')
  }, [maxReconnectAttempts])

  const send = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
      return true
    }
    console.warn('WebSocket not connected')
    return false
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setLastMessage(null)
  }, [])

  // Auto-connect on mount
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
    lastMessage,
    messages,
    connect,
    disconnect,
    send,
    clearMessages,
  }
}

// Specialized hooks for specific channels

export function useTasksWebSocket(
  onTaskUpdate?: (task: WebSocketMessage) => void
) {
  const [tasks, setTasks] = useState<any[]>([])

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'task_list') {
      setTasks(message.data?.active_tasks || [])
    } else if (message.type === 'task_update' || message.type === 'task_status') {
      onTaskUpdate?.(message)
    }
  }, [onTaskUpdate])

  const ws = useWebSocket('/ws/tasks', {
    onMessage: handleMessage,
  })

  const subscribeToTask = useCallback((taskId: string) => {
    ws.send({ action: 'subscribe', task_id: taskId })
  }, [ws])

  const refreshTasks = useCallback(() => {
    ws.send({ action: 'list' })
  }, [ws])

  return {
    ...ws,
    tasks,
    subscribeToTask,
    refreshTasks,
  }
}

export function useEmulatorWebSocket(emulatorId: string = 'default') {
  const [streaming, setStreaming] = useState(false)
  const [emulatorState, setEmulatorState] = useState<any>(null)
  const [signalHistory, setSignalHistory] = useState<any[]>([])

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'emulator_data' || message.type === 'emulator_state') {
      setEmulatorState(message.data)
      if (streaming) {
        setSignalHistory((prev) => [...prev.slice(-499), message.data]) // Keep last 500 samples
      }
    } else if (message.type === 'stream_started') {
      setStreaming(true)
    } else if (message.type === 'stream_stopped') {
      setStreaming(false)
    }
  }, [streaming])

  const ws = useWebSocket(`/ws/emulator/${emulatorId}`, {
    onMessage: handleMessage,
  })

  const startStreaming = useCallback((interval: number = 0.1) => {
    ws.send({ action: 'start_stream', interval })
  }, [ws])

  const stopStreaming = useCallback(() => {
    ws.send({ action: 'stop_stream' })
    setSignalHistory([])
  }, [ws])

  const getState = useCallback(() => {
    ws.send({ action: 'get_state' })
  }, [ws])

  return {
    ...ws,
    streaming,
    emulatorState,
    signalHistory,
    startStreaming,
    stopStreaming,
    getState,
  }
}

export function useSimulationWebSocket() {
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<any>(null)

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'simulation_started') {
      setIsRunning(true)
      setProgress(0)
      setResult(null)
    } else if (message.type === 'simulation_progress') {
      setProgress(message.data?.progress || 0)
    } else if (message.type === 'simulation_complete') {
      setIsRunning(false)
      setProgress(100)
      setResult(message.data)
    } else if (message.type === 'error') {
      setIsRunning(false)
      setProgress(0)
    }
  }, [])

  const ws = useWebSocket('/ws/simulation', {
    onMessage: handleMessage,
  })

  const startPropagation = useCallback((params: {
    orbital_elements: any
    duration: number
    time_step?: number
  }) => {
    setResult(null)
    setProgress(0)
    ws.send({
      action: 'propagate',
      ...params,
    })
  }, [ws])

  return {
    ...ws,
    isRunning,
    progress,
    result,
    startPropagation,
  }
}

export default useWebSocket
