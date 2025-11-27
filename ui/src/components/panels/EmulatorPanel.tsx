'use client'

/**
 * Emulator Panel Component
 *
 * Provides UI for optical bench emulator control and signal visualization
 */

import React, { useState } from 'react'
import { Activity, Play, Square, RotateCcw, Zap, AlertTriangle } from 'lucide-react'
import {
  useEmulatorStatus, useEmulatorHistory, useCreateEmulator,
  useEmulatorControl, useInjectEvent, EmulatorConfig
} from '@/hooks/useEmulator'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area
} from 'recharts'

export function EmulatorPanel() {
  const [emulatorId] = useState('default')
  const [showConfig, setShowConfig] = useState(false)

  // Config state
  const [config, setConfig] = useState<EmulatorConfig>({
    sample_rate: 10,
    wavelength: 1064e-9,
    noise_floor: 1e-6,
    initial_range: 100,
    initial_range_rate: 0.001,
  })

  // Event injection state
  const [eventType, setEventType] = useState<'vibration' | 'thermal' | 'glitch' | 'dropout'>('vibration')
  const [eventMagnitude, setEventMagnitude] = useState(0.1)
  const [eventDuration, setEventDuration] = useState(10)

  const { data: status, isLoading: isLoadingStatus } = useEmulatorStatus(emulatorId)
  const { data: history, isLoading: isLoadingHistory } = useEmulatorHistory(emulatorId, 500)
  const { create, isLoading: isCreating } = useCreateEmulator()
  const { start, stop, isStarting, isStopping } = useEmulatorControl(emulatorId)
  const { inject, isLoading: isInjecting } = useInjectEvent(emulatorId)

  const handleCreate = () => {
    create(config)
    setShowConfig(false)
  }

  const handleInjectEvent = () => {
    inject({
      event_type: eventType,
      magnitude: eventMagnitude,
      duration: eventDuration,
    })
  }

  // Prepare chart data
  const chartData = React.useMemo(() => {
    if (!history?.times) return []
    return history.times.map((t, i) => ({
      time: t,
      phase: history.phase?.[i] || 0,
      range: history.range?.[i] || 0,
      range_rate: (history.range_rate?.[i] || 0) * 1000,  // Convert to m/s
      noise: history.noise?.[i] || 0,
    }))
  }, [history])

  const isRunning = status?.status === 'running'
  const isLoading = isLoadingStatus || isLoadingHistory

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Activity className="w-7 h-7 text-orange-500" />
            Optical Bench Emulator
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Real-time laser interferometry signal emulation
          </p>
        </div>
        <button
          onClick={() => setShowConfig(true)}
          className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
        >
          Configure
        </button>
      </div>

      {/* Status Panel */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Emulator Status
          </h3>
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${
              isRunning
                ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
            }`}>
              <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
              {isRunning ? 'Running' : 'Stopped'}
            </div>
          </div>
        </div>

        {/* Current State */}
        {status && (
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
              <div className="text-sm text-blue-600 dark:text-blue-400">Time</div>
              <div className="text-xl font-bold text-blue-900 dark:text-blue-100">
                {status.current_time?.toFixed(2) || '0.00'} s
              </div>
            </div>
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
              <div className="text-sm text-green-600 dark:text-green-400">Phase</div>
              <div className="text-xl font-bold text-green-900 dark:text-green-100">
                {status.phase?.toFixed(4) || '0.0000'} rad
              </div>
            </div>
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <div className="text-sm text-purple-600 dark:text-purple-400">Range</div>
              <div className="text-xl font-bold text-purple-900 dark:text-purple-100">
                {status.range?.toFixed(3) || '0.000'} km
              </div>
            </div>
            <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-4">
              <div className="text-sm text-orange-600 dark:text-orange-400">Range Rate</div>
              <div className="text-xl font-bold text-orange-900 dark:text-orange-100">
                {((status.range_rate || 0) * 1000).toFixed(3)} m/s
              </div>
            </div>
          </div>
        )}

        {/* Control Buttons */}
        <div className="flex gap-3">
          {isRunning ? (
            <button
              onClick={() => stop()}
              disabled={isStopping}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {isStopping ? (
                <RotateCcw className="w-5 h-5 animate-spin" />
              ) : (
                <Square className="w-5 h-5" />
              )}
              Stop Emulator
            </button>
          ) : (
            <button
              onClick={() => start()}
              disabled={isStarting}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {isStarting ? (
                <RotateCcw className="w-5 h-5 animate-spin" />
              ) : (
                <Play className="w-5 h-5" />
              )}
              Start Emulator
            </button>
          )}
        </div>
      </div>

      {/* Signal Visualization */}
      {chartData.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Signal History
          </h3>

          {/* Phase Chart */}
          <div className="mb-6">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Phase Signal
            </h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="time" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1F2937',
                      border: 'none',
                      borderRadius: '8px',
                      color: '#F9FAFB'
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="phase"
                    name="Phase (rad)"
                    stroke="#F97316"
                    fill="#F9731633"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Range and Range Rate */}
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" stroke="#9CA3AF" />
                <YAxis yAxisId="range" stroke="#9CA3AF" />
                <YAxis yAxisId="rate" orientation="right" stroke="#9CA3AF" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#F9FAFB'
                  }}
                />
                <Legend />
                <Line
                  yAxisId="range"
                  type="monotone"
                  dataKey="range"
                  name="Range (km)"
                  stroke="#3B82F6"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="rate"
                  type="monotone"
                  dataKey="range_rate"
                  name="Range Rate (m/s)"
                  stroke="#10B981"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Event Injection */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-yellow-500" />
          Event Injection
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Inject anomalies to test system robustness
        </p>

        <div className="grid grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Event Type
            </label>
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value as any)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            >
              <option value="vibration">Vibration</option>
              <option value="thermal">Thermal Drift</option>
              <option value="glitch">Phase Glitch</option>
              <option value="dropout">Signal Dropout</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Magnitude
            </label>
            <input
              type="number"
              step="0.01"
              value={eventMagnitude}
              onChange={(e) => setEventMagnitude(parseFloat(e.target.value) || 0)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Duration (s)
            </label>
            <input
              type="number"
              value={eventDuration}
              onChange={(e) => setEventDuration(parseFloat(e.target.value) || 0)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
        </div>

        <button
          onClick={handleInjectEvent}
          disabled={!isRunning || isInjecting}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isInjecting ? (
            <RotateCcw className="w-5 h-5 animate-spin" />
          ) : (
            <Zap className="w-5 h-5" />
          )}
          Inject Event
        </button>
      </div>

      {/* Configuration Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Emulator Configuration
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Sample Rate (Hz)
                </label>
                <input
                  type="number"
                  value={config.sample_rate}
                  onChange={(e) => setConfig({ ...config, sample_rate: parseFloat(e.target.value) || 10 })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Initial Range (km)
                </label>
                <input
                  type="number"
                  value={config.initial_range}
                  onChange={(e) => setConfig({ ...config, initial_range: parseFloat(e.target.value) || 100 })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Initial Range Rate (km/s)
                </label>
                <input
                  type="number"
                  step="0.0001"
                  value={config.initial_range_rate}
                  onChange={(e) => setConfig({ ...config, initial_range_rate: parseFloat(e.target.value) || 0 })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Noise Floor (rad/√Hz)
                </label>
                <input
                  type="text"
                  value={config.noise_floor}
                  onChange={(e) => setConfig({ ...config, noise_floor: parseFloat(e.target.value) || 1e-6 })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowConfig(false)}
                className="flex-1 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={isCreating}
                className="flex-1 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {isCreating ? 'Creating...' : 'Create Emulator'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default EmulatorPanel
