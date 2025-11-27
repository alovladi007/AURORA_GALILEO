'use client'

/**
 * Control Panel Component
 *
 * Provides UI for formation control, LQR design, and maneuver planning
 */

import React, { useState } from 'react'
import { Settings, Play, RotateCcw, Target, Navigation } from 'lucide-react'
import { useLQRController, useManeuverPlanning, useStationKeeping, useFuelBudget, LQRConfig } from '@/hooks/useControl'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar
} from 'recharts'

export function ControlPanel() {
  const [mode, setMode] = useState<'lqr' | 'maneuver' | 'stationkeeping'>('lqr')

  // LQR config
  const [qPosition, setQPosition] = useState([1, 1, 1])
  const [qVelocity, setQVelocity] = useState([0.1, 0.1, 0.1])
  const [rControl, setRControl] = useState([1, 1, 1])

  // Maneuver planning
  const [initialState, setInitialState] = useState([0.1, 0, 0, 0, 0, 0])
  const [targetState, setTargetState] = useState([0, 0.1, 0, 0, 0, 0])
  const [timeHorizon, setTimeHorizon] = useState(3600)

  const { design: designLQR, isLoading: isDesigning, data: lqrResult } = useLQRController()
  const { plan: planManeuver, isLoading: isPlanning, data: maneuverResult } = useManeuverPlanning()
  const { compute: computeSK, isLoading: isComputingSK, data: skResult } = useStationKeeping()

  const handleDesignLQR = () => {
    // Create Hill-Clohessy-Wiltshire state matrices for demo
    const n = 0.00113  // Mean motion for ~400km altitude (rad/s)
    const A = [
      [0, 0, 0, 1, 0, 0],
      [0, 0, 0, 0, 1, 0],
      [0, 0, 0, 0, 0, 1],
      [3*n*n, 0, 0, 0, 2*n, 0],
      [0, 0, 0, -2*n, 0, 0],
      [0, 0, -n*n, 0, 0, 0],
    ]
    const B = [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ]

    designLQR({
      system_matrices: { A, B },
      config: {
        Q_position: qPosition,
        Q_velocity: qVelocity,
        R_control: rControl,
      }
    })
  }

  const handlePlanManeuver = () => {
    planManeuver({
      initial_state: initialState,
      target_state: targetState,
      time_horizon: timeHorizon,
      constraints: {
        max_delta_v: 0.01,  // 10 m/s max
        min_time_between: 600,  // 10 min between maneuvers
      }
    })
  }

  // Prepare eigenvalue chart data
  const eigenvalueData = lqrResult?.eigenvalues?.map((ev, i) => ({
    index: i + 1,
    real: typeof ev === 'number' ? ev : (ev as any).real || 0,
    imag: typeof ev === 'number' ? 0 : (ev as any).imag || 0,
  })) || []

  // Prepare maneuver chart data
  const maneuverData = maneuverResult?.delta_v?.map((dv, i) => ({
    maneuver: i + 1,
    time: maneuverResult.times?.[i] || i * 600,
    dvx: dv[0] * 1000,  // Convert to m/s
    dvy: dv[1] * 1000,
    dvz: dv[2] * 1000,
    magnitude: Math.sqrt(dv[0]**2 + dv[1]**2 + dv[2]**2) * 1000,
  })) || []

  const isLoading = isDesigning || isPlanning || isComputingSK

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Settings className="w-7 h-7 text-purple-500" />
            Formation Control
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            LQR controller design and maneuver planning
          </p>
        </div>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-2 p-1 bg-gray-100 dark:bg-gray-700 rounded-lg w-fit">
        <button
          onClick={() => setMode('lqr')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === 'lqr'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          LQR Controller
        </button>
        <button
          onClick={() => setMode('maneuver')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === 'maneuver'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          Maneuver Planning
        </button>
        <button
          onClick={() => setMode('stationkeeping')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            mode === 'stationkeeping'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          Station-Keeping
        </button>
      </div>

      {/* LQR Controller Design */}
      {mode === 'lqr' && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              LQR Weight Matrices
            </h3>

            <div className="space-y-4">
              {/* Q Position Weights */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Q (Position Weights) - [x, y, z]
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {['x', 'y', 'z'].map((axis, i) => (
                    <div key={axis}>
                      <input
                        type="number"
                        step="0.1"
                        value={qPosition[i]}
                        onChange={(e) => {
                          const newQ = [...qPosition]
                          newQ[i] = parseFloat(e.target.value) || 0
                          setQPosition(newQ)
                        }}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Q Velocity Weights */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Q (Velocity Weights) - [vx, vy, vz]
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {['vx', 'vy', 'vz'].map((axis, i) => (
                    <div key={axis}>
                      <input
                        type="number"
                        step="0.01"
                        value={qVelocity[i]}
                        onChange={(e) => {
                          const newQ = [...qVelocity]
                          newQ[i] = parseFloat(e.target.value) || 0
                          setQVelocity(newQ)
                        }}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* R Control Weights */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  R (Control Weights) - [ux, uy, uz]
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {['ux', 'uy', 'uz'].map((axis, i) => (
                    <div key={axis}>
                      <input
                        type="number"
                        step="0.1"
                        value={rControl[i]}
                        onChange={(e) => {
                          const newR = [...rControl]
                          newR[i] = parseFloat(e.target.value) || 0
                          setRControl(newR)
                        }}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <button
              onClick={handleDesignLQR}
              disabled={isDesigning}
              className="mt-6 w-full flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isDesigning ? (
                <>
                  <RotateCcw className="w-5 h-5 animate-spin" />
                  Computing...
                </>
              ) : (
                <>
                  <Target className="w-5 h-5" />
                  Design Controller
                </>
              )}
            </button>
          </div>

          {/* LQR Results */}
          {lqrResult && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Controller Design Results
              </h3>

              {/* Status */}
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className={`${lqrResult.controllable ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'} rounded-lg p-4`}>
                  <div className={`text-sm ${lqrResult.controllable ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    Controllability
                  </div>
                  <div className={`text-xl font-bold ${lqrResult.controllable ? 'text-green-900 dark:text-green-100' : 'text-red-900 dark:text-red-100'}`}>
                    {lqrResult.controllable ? 'System Controllable' : 'Not Controllable'}
                  </div>
                </div>
                <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
                  <div className="text-sm text-purple-600 dark:text-purple-400">Gain Matrix Size</div>
                  <div className="text-xl font-bold text-purple-900 dark:text-purple-100">
                    {lqrResult.K_gain?.length || 0} x {lqrResult.K_gain?.[0]?.length || 0}
                  </div>
                </div>
              </div>

              {/* Closed-Loop Poles */}
              {eigenvalueData.length > 0 && (
                <div>
                  <h4 className="text-md font-medium text-gray-900 dark:text-white mb-3">
                    Closed-Loop Eigenvalues
                  </h4>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={eigenvalueData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="index" stroke="#9CA3AF" />
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
                        <Bar dataKey="real" name="Real Part" fill="#8B5CF6" />
                        <Bar dataKey="imag" name="Imaginary Part" fill="#EC4899" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Maneuver Planning */}
      {mode === 'maneuver' && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Maneuver Planning Configuration
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Initial State [x, y, z, vx, vy, vz] (km, km/s)
                </label>
                <div className="grid grid-cols-6 gap-2">
                  {initialState.map((val, i) => (
                    <input
                      key={i}
                      type="number"
                      step="0.01"
                      value={val}
                      onChange={(e) => {
                        const newState = [...initialState]
                        newState[i] = parseFloat(e.target.value) || 0
                        setInitialState(newState)
                      }}
                      className="px-2 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                    />
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Target State [x, y, z, vx, vy, vz] (km, km/s)
                </label>
                <div className="grid grid-cols-6 gap-2">
                  {targetState.map((val, i) => (
                    <input
                      key={i}
                      type="number"
                      step="0.01"
                      value={val}
                      onChange={(e) => {
                        const newState = [...targetState]
                        newState[i] = parseFloat(e.target.value) || 0
                        setTargetState(newState)
                      }}
                      className="px-2 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                    />
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Time Horizon (seconds)
                </label>
                <input
                  type="number"
                  value={timeHorizon}
                  onChange={(e) => setTimeHorizon(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>

            <button
              onClick={handlePlanManeuver}
              disabled={isPlanning}
              className="mt-6 w-full flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPlanning ? (
                <>
                  <RotateCcw className="w-5 h-5 animate-spin" />
                  Planning...
                </>
              ) : (
                <>
                  <Navigation className="w-5 h-5" />
                  Plan Maneuvers
                </>
              )}
            </button>
          </div>

          {/* Maneuver Results */}
          {maneuverResult && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Maneuver Plan
              </h3>

              {/* Summary */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
                  <div className="text-sm text-purple-600 dark:text-purple-400">Number of Maneuvers</div>
                  <div className="text-2xl font-bold text-purple-900 dark:text-purple-100">
                    {maneuverResult.delta_v?.length || 0}
                  </div>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                  <div className="text-sm text-blue-600 dark:text-blue-400">Total Delta-V</div>
                  <div className="text-2xl font-bold text-blue-900 dark:text-blue-100">
                    {((maneuverResult.total_delta_v || 0) * 1000).toFixed(2)} m/s
                  </div>
                </div>
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                  <div className="text-sm text-green-600 dark:text-green-400">Fuel Mass</div>
                  <div className="text-2xl font-bold text-green-900 dark:text-green-100">
                    {(maneuverResult.fuel_mass || 0).toFixed(3)} kg
                  </div>
                </div>
              </div>

              {/* Maneuver Chart */}
              {maneuverData.length > 0 && (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={maneuverData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="maneuver" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" label={{ value: 'm/s', angle: -90, position: 'insideLeft', fill: '#9CA3AF' }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1F2937',
                          border: 'none',
                          borderRadius: '8px',
                          color: '#F9FAFB'
                        }}
                      />
                      <Legend />
                      <Bar dataKey="dvx" name="ΔVx" fill="#3B82F6" />
                      <Bar dataKey="dvy" name="ΔVy" fill="#10B981" />
                      <Bar dataKey="dvz" name="ΔVz" fill="#F59E0B" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Station-Keeping */}
      {mode === 'stationkeeping' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Station-Keeping
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-6">
            Compute station-keeping maneuvers to maintain reference orbit
          </p>

          <div className="text-center py-8">
            <Target className="w-16 h-16 mx-auto text-gray-400 mb-4" />
            <p className="text-gray-500 dark:text-gray-400">
              Configure orbit parameters and tolerance bounds to compute station-keeping maneuvers
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default ControlPanel
