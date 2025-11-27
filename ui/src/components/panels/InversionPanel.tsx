'use client'

/**
 * Inversion Panel Component
 *
 * Provides UI for gravity field inversion operations
 */

import React, { useState } from 'react'
import { BarChart3, Play, RotateCcw, Download, Upload } from 'lucide-react'
import { useGravityEstimation, useTikhonovInversion, useGravityGrid, InversionConfig } from '@/hooks/useInversion'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter, ZAxis
} from 'recharts'

export function InversionPanel() {
  const [algorithm, setAlgorithm] = useState<InversionConfig['algorithm']>('tikhonov')
  const [degreeMax, setDegreeMax] = useState(60)
  const [regularization, setRegularization] = useState(1e-6)
  const [maxIterations, setMaxIterations] = useState(100)

  // Demo data for visualization
  const [demoMode, setDemoMode] = useState(true)

  const { estimate, isLoading: isEstimating, data: estimationResult } = useGravityEstimation()
  const { computeGrid, isLoading: isGridding, data: gridResult } = useGravityGrid()

  const handleRunInversion = () => {
    if (demoMode) {
      // Generate synthetic observations for demo
      const syntheticObs: number[][] = []
      for (let lat = -80; lat <= 80; lat += 10) {
        for (let lon = -180; lon <= 180; lon += 20) {
          syntheticObs.push([
            100 + Math.random() * 10,  // range
            Math.random() * 2 * Math.PI,  // phase
            lat,
            lon,
            450  // altitude
          ])
        }
      }

      estimate({
        observations: syntheticObs,
        config: {
          algorithm,
          degree_max: degreeMax,
          regularization_parameter: regularization,
          max_iterations: maxIterations,
        }
      })
    }
  }

  const handleComputeGrid = () => {
    if (estimationResult?.coefficients) {
      computeGrid({
        coefficients: estimationResult.coefficients,
        lat_range: [-90, 90],
        lon_range: [-180, 180],
        resolution: 2,
      })
    }
  }

  // Prepare convergence chart data
  const convergenceData = estimationResult?.residuals?.map((r, i) => ({
    iteration: i + 1,
    residual: r,
  })) || []

  // Prepare gravity anomaly heatmap data
  const heatmapData = React.useMemo(() => {
    if (!gridResult?.values) return []

    const data: { lat: number; lon: number; value: number }[] = []
    gridResult.latitudes.forEach((lat, i) => {
      gridResult.longitudes.forEach((lon, j) => {
        data.push({
          lat,
          lon,
          value: gridResult.values[i][j],
        })
      })
    })
    return data
  }, [gridResult])

  const isLoading = isEstimating || isGridding

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <BarChart3 className="w-7 h-7 text-green-500" />
            Gravity Inversion
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Estimate gravity field from satellite measurements
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
            <input
              type="checkbox"
              checked={demoMode}
              onChange={(e) => setDemoMode(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600"
            />
            Demo Mode
          </label>
        </div>
      </div>

      {/* Algorithm Selection */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Inversion Configuration
        </h3>

        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Algorithm
            </label>
            <select
              value={algorithm}
              onChange={(e) => setAlgorithm(e.target.value as InversionConfig['algorithm'])}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            >
              <option value="tikhonov">Tikhonov Regularization</option>
              <option value="variational">Variational</option>
              <option value="mascon">Mascon</option>
              <option value="spherical_harmonic">Spherical Harmonic</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Maximum Degree
            </label>
            <input
              type="number"
              value={degreeMax}
              onChange={(e) => setDegreeMax(parseInt(e.target.value) || 0)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Regularization Parameter
            </label>
            <input
              type="text"
              value={regularization}
              onChange={(e) => setRegularization(parseFloat(e.target.value) || 0)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Max Iterations
            </label>
            <input
              type="number"
              value={maxIterations}
              onChange={(e) => setMaxIterations(parseInt(e.target.value) || 1)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
        </div>

        {/* Data Input */}
        {!demoMode && (
          <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600">
            <div className="flex items-center justify-center gap-3 text-gray-500 dark:text-gray-400">
              <Upload className="w-6 h-6" />
              <span>Drag & drop observation data or click to upload</span>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            onClick={handleRunInversion}
            disabled={isLoading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isEstimating ? (
              <>
                <RotateCcw className="w-5 h-5 animate-spin" />
                Running Inversion...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                Run Inversion
              </>
            )}
          </button>
          {estimationResult?.coefficients && (
            <button
              onClick={handleComputeGrid}
              disabled={isGridding}
              className="px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {isGridding ? (
                <RotateCcw className="w-5 h-5 animate-spin" />
              ) : (
                'Compute Grid'
              )}
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      {estimationResult && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Inversion Results
          </h3>

          {/* Convergence Info */}
          {estimationResult.convergence && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                <div className="text-sm text-blue-600 dark:text-blue-400">Iterations</div>
                <div className="text-2xl font-bold text-blue-900 dark:text-blue-100">
                  {estimationResult.convergence.iterations}
                </div>
              </div>
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                <div className="text-sm text-green-600 dark:text-green-400">Final Residual</div>
                <div className="text-2xl font-bold text-green-900 dark:text-green-100">
                  {estimationResult.convergence.final_residual.toExponential(2)}
                </div>
              </div>
              <div className={`${estimationResult.convergence.converged ? 'bg-green-50 dark:bg-green-900/20' : 'bg-yellow-50 dark:bg-yellow-900/20'} rounded-lg p-4`}>
                <div className={`text-sm ${estimationResult.convergence.converged ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                  Status
                </div>
                <div className={`text-2xl font-bold ${estimationResult.convergence.converged ? 'text-green-900 dark:text-green-100' : 'text-yellow-900 dark:text-yellow-100'}`}>
                  {estimationResult.convergence.converged ? 'Converged' : 'Not Converged'}
                </div>
              </div>
            </div>
          )}

          {/* Convergence Chart */}
          {convergenceData.length > 0 && (
            <div className="mb-6">
              <h4 className="text-md font-medium text-gray-900 dark:text-white mb-3">
                Convergence History
              </h4>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={convergenceData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="iteration" stroke="#9CA3AF" />
                    <YAxis stroke="#9CA3AF" scale="log" domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#F9FAFB'
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="residual"
                      name="Residual"
                      stroke="#10B981"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Statistics */}
          {estimationResult.statistics && (
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                <div className="text-xs text-gray-500 dark:text-gray-400">Mean</div>
                <div className="text-lg font-semibold text-gray-900 dark:text-white">
                  {estimationResult.statistics.mean.toFixed(2)} mGal
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                <div className="text-xs text-gray-500 dark:text-gray-400">Std Dev</div>
                <div className="text-lg font-semibold text-gray-900 dark:text-white">
                  {estimationResult.statistics.std.toFixed(2)} mGal
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                <div className="text-xs text-gray-500 dark:text-gray-400">Min</div>
                <div className="text-lg font-semibold text-gray-900 dark:text-white">
                  {estimationResult.statistics.min.toFixed(2)} mGal
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                <div className="text-xs text-gray-500 dark:text-gray-400">Max</div>
                <div className="text-lg font-semibold text-gray-900 dark:text-white">
                  {estimationResult.statistics.max.toFixed(2)} mGal
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Gravity Grid Visualization */}
      {gridResult && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Gravity Anomaly Map
            </h3>
            <button
              onClick={() => {
                const blob = new Blob([JSON.stringify(gridResult, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = 'gravity_grid.json'
                a.click()
              }}
              className="flex items-center gap-2 px-3 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors text-sm"
            >
              <Download className="w-4 h-4" />
              Export
            </button>
          </div>

          {/* Heatmap visualization */}
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  type="number"
                  dataKey="lon"
                  domain={[-180, 180]}
                  stroke="#9CA3AF"
                  label={{ value: 'Longitude', position: 'bottom', fill: '#9CA3AF' }}
                />
                <YAxis
                  type="number"
                  dataKey="lat"
                  domain={[-90, 90]}
                  stroke="#9CA3AF"
                  label={{ value: 'Latitude', angle: -90, position: 'left', fill: '#9CA3AF' }}
                />
                <ZAxis type="number" dataKey="value" range={[10, 100]} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#F9FAFB'
                  }}
                  formatter={(value: number) => [`${value.toFixed(2)} mGal`, 'Anomaly']}
                />
                <Scatter
                  data={heatmapData}
                  fill="#8884d8"
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 flex items-center justify-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-blue-500" />
              <span className="text-gray-600 dark:text-gray-400">Low ({gridResult.statistics?.min?.toFixed(1)} mGal)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-purple-500" />
              <span className="text-gray-600 dark:text-gray-400">High ({gridResult.statistics?.max?.toFixed(1)} mGal)</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default InversionPanel
