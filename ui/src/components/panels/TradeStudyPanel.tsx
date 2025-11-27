'use client'

/**
 * Trade Study Panel Component
 *
 * Provides UI for mission design trade studies and Pareto analysis
 */

import React, { useState } from 'react'
import { TrendingUp, Play, RotateCcw, Download, Target } from 'lucide-react'
import {
  useBaselineStudy, useOrbitStudy, useOpticalStudy,
  useParetoFront, useSensitivityAnalysis, TradeStudyResult
} from '@/hooks/useTradeStudy'
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, BarChart, Bar
} from 'recharts'

export function TradeStudyPanel() {
  const [studyType, setStudyType] = useState<'baseline' | 'orbit' | 'optical'>('baseline')

  // Baseline study config
  const [baselineRange, setBaselineRange] = useState<[number, number]>([10, 500])
  const [orbitAltitude, setOrbitAltitude] = useState(450)

  // Orbit study config
  const [altitudeRange, setAltitudeRange] = useState<[number, number]>([300, 600])
  const [inclinationRange, setInclinationRange] = useState<[number, number]>([60, 98])

  // Optical study config
  const [powerRange, setPowerRange] = useState<[number, number]>([0.1, 2])
  const [apertureRange, setApertureRange] = useState<[number, number]>([0.05, 0.2])

  // Common config
  const [nSamples, setNSamples] = useState(50)
  const [objectives, setObjectives] = useState(['gravity_accuracy', 'mass', 'power'])

  const { run: runBaseline, isLoading: isRunningBaseline, data: baselineResult } = useBaselineStudy()
  const { run: runOrbit, isLoading: isRunningOrbit, data: orbitResult } = useOrbitStudy()
  const { run: runOptical, isLoading: isRunningOptical, data: opticalResult } = useOpticalStudy()
  const { compute: computePareto, isLoading: isComputingPareto, data: paretoPoints } = useParetoFront()
  const { analyze: analyzeSensitivity, isLoading: isAnalyzing, data: sensitivityData } = useSensitivityAnalysis()

  const handleRunStudy = () => {
    switch (studyType) {
      case 'baseline':
        runBaseline({
          baseline_range: baselineRange,
          n_samples: nSamples,
          orbit_altitude: orbitAltitude,
          objectives,
        })
        break
      case 'orbit':
        runOrbit({
          altitude_range: altitudeRange,
          inclination_range: inclinationRange,
          n_samples: nSamples,
          objectives,
        })
        break
      case 'optical':
        runOptical({
          power_range: powerRange,
          aperture_range: apertureRange,
          n_samples: nSamples,
          objectives,
        })
        break
    }
  }

  const currentResult = studyType === 'baseline' ? baselineResult
    : studyType === 'orbit' ? orbitResult
    : opticalResult

  // Prepare scatter plot data for Pareto front
  const scatterData = React.useMemo(() => {
    if (!currentResult?.objective_values) return []

    const obj1 = objectives[0]
    const obj2 = objectives[1]

    return (currentResult.objective_values[obj1] || []).map((v1, i) => ({
      [obj1]: v1,
      [obj2]: currentResult.objective_values[obj2]?.[i] || 0,
      isPareto: currentResult.pareto_indices?.includes(i) || false,
    }))
  }, [currentResult, objectives])

  // Prepare sensitivity bar chart data
  const sensitivityChartData = sensitivityData?.map(s => ({
    parameter: s.parameter,
    first_order: s.first_order,
    total_order: s.total_order,
  })) || []

  const isLoading = isRunningBaseline || isRunningOrbit || isRunningOptical

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <TrendingUp className="w-7 h-7 text-indigo-500" />
            Trade Studies
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Mission design trade space exploration and Pareto analysis
          </p>
        </div>
      </div>

      {/* Study Type Toggle */}
      <div className="flex gap-2 p-1 bg-gray-100 dark:bg-gray-700 rounded-lg w-fit">
        <button
          onClick={() => setStudyType('baseline')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            studyType === 'baseline'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          Baseline Length
        </button>
        <button
          onClick={() => setStudyType('orbit')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            studyType === 'orbit'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          Orbit Parameters
        </button>
        <button
          onClick={() => setStudyType('optical')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            studyType === 'optical'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          Optical System
        </button>
      </div>

      {/* Configuration */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Study Configuration
        </h3>

        <div className="grid grid-cols-2 gap-6 mb-6">
          {/* Study-specific parameters */}
          {studyType === 'baseline' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Baseline Range (km)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    value={baselineRange[0]}
                    onChange={(e) => setBaselineRange([parseFloat(e.target.value) || 0, baselineRange[1]])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Min"
                  />
                  <input
                    type="number"
                    value={baselineRange[1]}
                    onChange={(e) => setBaselineRange([baselineRange[0], parseFloat(e.target.value) || 0])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Max"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Orbit Altitude (km)
                </label>
                <input
                  type="number"
                  value={orbitAltitude}
                  onChange={(e) => setOrbitAltitude(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </>
          )}

          {studyType === 'orbit' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Altitude Range (km)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    value={altitudeRange[0]}
                    onChange={(e) => setAltitudeRange([parseFloat(e.target.value) || 0, altitudeRange[1]])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Min"
                  />
                  <input
                    type="number"
                    value={altitudeRange[1]}
                    onChange={(e) => setAltitudeRange([altitudeRange[0], parseFloat(e.target.value) || 0])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Max"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Inclination Range (deg)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    value={inclinationRange[0]}
                    onChange={(e) => setInclinationRange([parseFloat(e.target.value) || 0, inclinationRange[1]])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Min"
                  />
                  <input
                    type="number"
                    value={inclinationRange[1]}
                    onChange={(e) => setInclinationRange([inclinationRange[0], parseFloat(e.target.value) || 0])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Max"
                  />
                </div>
              </div>
            </>
          )}

          {studyType === 'optical' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Laser Power Range (W)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    step="0.1"
                    value={powerRange[0]}
                    onChange={(e) => setPowerRange([parseFloat(e.target.value) || 0, powerRange[1]])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Min"
                  />
                  <input
                    type="number"
                    step="0.1"
                    value={powerRange[1]}
                    onChange={(e) => setPowerRange([powerRange[0], parseFloat(e.target.value) || 0])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Max"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Aperture Range (m)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    step="0.01"
                    value={apertureRange[0]}
                    onChange={(e) => setApertureRange([parseFloat(e.target.value) || 0, apertureRange[1]])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Min"
                  />
                  <input
                    type="number"
                    step="0.01"
                    value={apertureRange[1]}
                    onChange={(e) => setApertureRange([apertureRange[0], parseFloat(e.target.value) || 0])}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Max"
                  />
                </div>
              </div>
            </>
          )}
        </div>

        {/* Common parameters */}
        <div className="grid grid-cols-2 gap-6 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Number of Samples
            </label>
            <input
              type="number"
              value={nSamples}
              onChange={(e) => setNSamples(parseInt(e.target.value) || 10)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Objectives
            </label>
            <div className="flex flex-wrap gap-2">
              {['gravity_accuracy', 'mass', 'power', 'cost', 'lifetime'].map((obj) => (
                <label key={obj} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={objectives.includes(obj)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setObjectives([...objectives, obj])
                      } else {
                        setObjectives(objectives.filter(o => o !== obj))
                      }
                    }}
                    className="rounded border-gray-300 dark:border-gray-600"
                  />
                  <span className="text-gray-700 dark:text-gray-300">{obj}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <button
          onClick={handleRunStudy}
          disabled={isLoading}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <>
              <RotateCcw className="w-5 h-5 animate-spin" />
              Running Study...
            </>
          ) : (
            <>
              <Play className="w-5 h-5" />
              Run Trade Study
            </>
          )}
        </button>
      </div>

      {/* Results */}
      {currentResult && (
        <div className="space-y-6">
          {/* Pareto Front */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <Target className="w-5 h-5 text-indigo-500" />
                Pareto Front
              </h3>
              <button
                onClick={() => {
                  const blob = new Blob([JSON.stringify(currentResult, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `trade_study_${studyType}.json`
                  a.click()
                }}
                className="flex items-center gap-2 px-3 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors text-sm"
              >
                <Download className="w-4 h-4" />
                Export
              </button>
            </div>

            {/* Summary Stats */}
            {currentResult.optimal_point && (
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg p-4">
                  <div className="text-sm text-indigo-600 dark:text-indigo-400">Pareto Points</div>
                  <div className="text-2xl font-bold text-indigo-900 dark:text-indigo-100">
                    {currentResult.pareto_indices?.length || 0}
                  </div>
                </div>
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                  <div className="text-sm text-green-600 dark:text-green-400">Total Samples</div>
                  <div className="text-2xl font-bold text-green-900 dark:text-green-100">
                    {nSamples}
                  </div>
                </div>
                <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
                  <div className="text-sm text-purple-600 dark:text-purple-400">Objectives</div>
                  <div className="text-2xl font-bold text-purple-900 dark:text-purple-100">
                    {objectives.length}
                  </div>
                </div>
              </div>
            )}

            {/* Scatter Plot */}
            {scatterData.length > 0 && objectives.length >= 2 && (
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 20, right: 20, bottom: 60, left: 60 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      type="number"
                      dataKey={objectives[0]}
                      name={objectives[0]}
                      stroke="#9CA3AF"
                      label={{ value: objectives[0], position: 'bottom', fill: '#9CA3AF', offset: 40 }}
                    />
                    <YAxis
                      type="number"
                      dataKey={objectives[1]}
                      name={objectives[1]}
                      stroke="#9CA3AF"
                      label={{ value: objectives[1], angle: -90, position: 'left', fill: '#9CA3AF', offset: 40 }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#F9FAFB'
                      }}
                    />
                    <Legend />
                    <Scatter
                      name="Design Points"
                      data={scatterData.filter(d => !d.isPareto)}
                      fill="#6B7280"
                    />
                    <Scatter
                      name="Pareto Front"
                      data={scatterData.filter(d => d.isPareto)}
                      fill="#6366F1"
                    />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Sensitivity Analysis */}
          {sensitivityChartData.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Sensitivity Analysis
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sensitivityChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="parameter" stroke="#9CA3AF" />
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
                    <Bar dataKey="first_order" name="First Order" fill="#6366F1" />
                    <Bar dataKey="total_order" name="Total Order" fill="#EC4899" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default TradeStudyPanel
