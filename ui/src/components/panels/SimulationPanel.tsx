'use client'

/**
 * Simulation Panel Component
 *
 * Provides UI for orbit propagation and formation flying simulation
 */

import React, { useState } from 'react'
import { Satellite, Play, RotateCcw, Download, Settings } from 'lucide-react'
import { useOrbitPropagation, useFormationSimulation, OrbitalElements } from '@/hooks/useSimulation'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'

interface SimulationPanelProps {
  onTrajectoryComputed?: (trajectory: number[][]) => void
}

export function SimulationPanel({ onTrajectoryComputed }: SimulationPanelProps) {
  const [mode, setMode] = useState<'single' | 'formation'>('single')
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Orbital elements state
  const [orbitalElements, setOrbitalElements] = useState<OrbitalElements>({
    semi_major_axis: 6878,      // ~500km altitude
    eccentricity: 0.001,
    inclination: 97.4,          // Sun-synchronous
    raan: 0,
    argument_of_perigee: 0,
    true_anomaly: 0,
  })

  // Simulation parameters
  const [duration, setDuration] = useState(5400)     // 1.5 orbits
  const [timeStep, setTimeStep] = useState(60)       // 1 minute

  // Formation offset
  const [deputyOffset, setDeputyOffset] = useState([0.1, 0, 0, 0, 0, 0])

  const { propagate, isLoading: isPropagating, data: propagationResult } = useOrbitPropagation()
  const { simulate, isLoading: isSimulating, data: formationResult } = useFormationSimulation()

  const handlePropagate = () => {
    if (mode === 'single') {
      propagate({
        orbital_elements: orbitalElements,
        duration,
        time_step: timeStep,
      })
    } else {
      simulate({
        chief_elements: orbitalElements,
        deputy_offsets: deputyOffset,
        duration,
        time_step: timeStep,
      })
    }
  }

  // Prepare chart data
  const chartData = React.useMemo(() => {
    if (mode === 'single' && propagationResult?.trajectory) {
      return propagationResult.trajectory.map((state, i) => ({
        time: (propagationResult.times?.[i] || i * timeStep) / 60,
        x: state[0],
        y: state[1],
        z: state[2],
        altitude: Math.sqrt(state[0]**2 + state[1]**2 + state[2]**2) - 6378,
      }))
    }
    if (mode === 'formation' && formationResult?.relative_trajectory) {
      return formationResult.relative_trajectory.map((state, i) => ({
        time: (formationResult.times?.[i] || i * timeStep) / 60,
        x: state[0] * 1000,  // Convert to meters
        y: state[1] * 1000,
        z: state[2] * 1000,
        baseline: Math.sqrt(state[0]**2 + state[1]**2 + state[2]**2) * 1000,
      }))
    }
    return []
  }, [propagationResult, formationResult, mode, timeStep])

  const isLoading = isPropagating || isSimulating

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Satellite className="w-7 h-7 text-blue-500" />
            Orbit Simulation
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Propagate orbits and simulate formation flying
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="px-3 py-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-2 p-1 bg-gray-100 dark:bg-gray-700 rounded-lg w-fit">
        <button
          onClick={() => setMode('single')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === 'single'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          Single Orbit
        </button>
        <button
          onClick={() => setMode('formation')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === 'formation'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          Formation Flying
        </button>
      </div>

      {/* Orbital Elements Input */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Orbital Elements
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Semi-major Axis (km)
            </label>
            <input
              type="number"
              value={orbitalElements.semi_major_axis}
              onChange={(e) => setOrbitalElements({
                ...orbitalElements,
                semi_major_axis: parseFloat(e.target.value) || 0
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Eccentricity
            </label>
            <input
              type="number"
              step="0.001"
              value={orbitalElements.eccentricity}
              onChange={(e) => setOrbitalElements({
                ...orbitalElements,
                eccentricity: parseFloat(e.target.value) || 0
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Inclination (deg)
            </label>
            <input
              type="number"
              step="0.1"
              value={orbitalElements.inclination}
              onChange={(e) => setOrbitalElements({
                ...orbitalElements,
                inclination: parseFloat(e.target.value) || 0
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              RAAN (deg)
            </label>
            <input
              type="number"
              step="1"
              value={orbitalElements.raan}
              onChange={(e) => setOrbitalElements({
                ...orbitalElements,
                raan: parseFloat(e.target.value) || 0
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Arg. of Perigee (deg)
            </label>
            <input
              type="number"
              step="1"
              value={orbitalElements.argument_of_perigee}
              onChange={(e) => setOrbitalElements({
                ...orbitalElements,
                argument_of_perigee: parseFloat(e.target.value) || 0
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              True Anomaly (deg)
            </label>
            <input
              type="number"
              step="1"
              value={orbitalElements.true_anomaly}
              onChange={(e) => setOrbitalElements({
                ...orbitalElements,
                true_anomaly: parseFloat(e.target.value) || 0
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
        </div>

        {/* Formation offset (only show in formation mode) */}
        {mode === 'formation' && (
          <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <h4 className="text-md font-medium text-gray-900 dark:text-white mb-3">
              Deputy Offset (relative to chief)
            </h4>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
              {['x (km)', 'y (km)', 'z (km)', 'vx (km/s)', 'vy (km/s)', 'vz (km/s)'].map((label, i) => (
                <div key={label}>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                    {label}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={deputyOffset[i]}
                    onChange={(e) => {
                      const newOffset = [...deputyOffset]
                      newOffset[i] = parseFloat(e.target.value) || 0
                      setDeputyOffset(newOffset)
                    }}
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Simulation Parameters */}
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Duration (seconds)
              </label>
              <input
                type="number"
                value={duration}
                onChange={(e) => setDuration(parseInt(e.target.value) || 0)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Time Step (seconds)
              </label>
              <input
                type="number"
                value={timeStep}
                onChange={(e) => setTimeStep(parseInt(e.target.value) || 1)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-6 flex gap-3">
          <button
            onClick={handlePropagate}
            disabled={isLoading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <RotateCcw className="w-5 h-5 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                Run Simulation
              </>
            )}
          </button>
          {chartData.length > 0 && (
            <button
              onClick={() => {
                const blob = new Blob([JSON.stringify(chartData, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = 'trajectory.json'
                a.click()
              }}
              className="px-4 py-3 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
            >
              <Download className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      {chartData.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {mode === 'single' ? 'Orbit Trajectory' : 'Relative Motion'}
          </h3>

          {/* Orbital Parameters */}
          {mode === 'single' && propagationResult?.orbital_parameters && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                <div className="text-xs text-blue-600 dark:text-blue-400">Period</div>
                <div className="text-lg font-semibold text-blue-900 dark:text-blue-100">
                  {(propagationResult.orbital_parameters.period / 60).toFixed(1)} min
                </div>
              </div>
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
                <div className="text-xs text-green-600 dark:text-green-400">Apogee</div>
                <div className="text-lg font-semibold text-green-900 dark:text-green-100">
                  {propagationResult.orbital_parameters.apogee.toFixed(1)} km
                </div>
              </div>
              <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3">
                <div className="text-xs text-purple-600 dark:text-purple-400">Perigee</div>
                <div className="text-lg font-semibold text-purple-900 dark:text-purple-100">
                  {propagationResult.orbital_parameters.perigee.toFixed(1)} km
                </div>
              </div>
              <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3">
                <div className="text-xs text-orange-600 dark:text-orange-400">V @ Apogee</div>
                <div className="text-lg font-semibold text-orange-900 dark:text-orange-100">
                  {propagationResult.orbital_parameters.velocity_apogee.toFixed(2)} km/s
                </div>
              </div>
              <div className="bg-pink-50 dark:bg-pink-900/20 rounded-lg p-3">
                <div className="text-xs text-pink-600 dark:text-pink-400">V @ Perigee</div>
                <div className="text-lg font-semibold text-pink-900 dark:text-pink-100">
                  {propagationResult.orbital_parameters.velocity_perigee.toFixed(2)} km/s
                </div>
              </div>
            </div>
          )}

          {/* Chart */}
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="time"
                  stroke="#9CA3AF"
                  label={{ value: 'Time (min)', position: 'bottom', fill: '#9CA3AF' }}
                />
                <YAxis stroke="#9CA3AF" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#F9FAFB'
                  }}
                />
                <Legend />
                {mode === 'single' ? (
                  <Line
                    type="monotone"
                    dataKey="altitude"
                    name="Altitude (km)"
                    stroke="#3B82F6"
                    strokeWidth={2}
                    dot={false}
                  />
                ) : (
                  <>
                    <Line type="monotone" dataKey="x" name="X (m)" stroke="#3B82F6" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="y" name="Y (m)" stroke="#10B981" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="z" name="Z (m)" stroke="#F59E0B" strokeWidth={2} dot={false} />
                  </>
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}

export default SimulationPanel
