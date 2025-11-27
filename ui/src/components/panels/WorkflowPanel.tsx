'use client'

/**
 * Workflow Panel Component
 *
 * End-to-end pipeline management for mission workflows
 */

import React, { useState } from 'react'
import { PlayCircle, Pause, Square, Clock, CheckCircle, XCircle, AlertTriangle, Plus, Trash2, RefreshCw, ChevronRight } from 'lucide-react'

interface WorkflowStep {
  id: string
  name: string
  type: 'simulation' | 'inversion' | 'ml' | 'control' | 'calibration' | 'export'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  duration?: number
  result?: any
}

interface Workflow {
  id: string
  name: string
  description: string
  steps: WorkflowStep[]
  status: 'idle' | 'running' | 'completed' | 'failed' | 'paused'
  progress: number
  createdAt: string
  startedAt?: string
  completedAt?: string
}

const PREDEFINED_WORKFLOWS: Omit<Workflow, 'id' | 'createdAt'>[] = [
  {
    name: 'Full Mission Pipeline',
    description: 'Complete orbit-to-gravity field workflow',
    steps: [
      { id: '1', name: 'Orbit Propagation', type: 'simulation', status: 'pending' },
      { id: '2', name: 'Formation Control', type: 'control', status: 'pending' },
      { id: '3', name: 'Gravity Inversion', type: 'inversion', status: 'pending' },
      { id: '4', name: 'PINN Enhancement', type: 'ml', status: 'pending' },
      { id: '5', name: 'Export Results', type: 'export', status: 'pending' },
    ],
    status: 'idle',
    progress: 0,
  },
  {
    name: 'Calibration Pipeline',
    description: 'Instrument calibration and validation',
    steps: [
      { id: '1', name: 'Phase Noise Analysis', type: 'calibration', status: 'pending' },
      { id: '2', name: 'Allan Deviation', type: 'calibration', status: 'pending' },
      { id: '3', name: 'Noise Budget', type: 'calibration', status: 'pending' },
    ],
    status: 'idle',
    progress: 0,
  },
  {
    name: 'ML Training Pipeline',
    description: 'Train and validate ML models',
    steps: [
      { id: '1', name: 'Generate Training Data', type: 'simulation', status: 'pending' },
      { id: '2', name: 'Train PINN', type: 'ml', status: 'pending' },
      { id: '3', name: 'Train U-Net', type: 'ml', status: 'pending' },
      { id: '4', name: 'Validate Models', type: 'ml', status: 'pending' },
    ],
    status: 'idle',
    progress: 0,
  },
]

export function WorkflowPanel() {
  const [workflows, setWorkflows] = useState<Workflow[]>([
    {
      id: '1',
      ...PREDEFINED_WORKFLOWS[0],
      createdAt: new Date().toISOString(),
    },
  ])
  const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>('1')
  const [showCreateModal, setShowCreateModal] = useState(false)

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <Clock className="w-4 h-4 text-gray-400" />
      case 'running':
        return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-500" />
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />
      case 'skipped':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />
      default:
        return <Clock className="w-4 h-4 text-gray-400" />
    }
  }

  const getStepTypeColor = (type: string) => {
    switch (type) {
      case 'simulation':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'inversion':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
      case 'ml':
        return 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300'
      case 'control':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
      case 'calibration':
        return 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300'
      case 'export':
        return 'bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300'
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
    }
  }

  const handleStartWorkflow = (workflowId: string) => {
    setWorkflows(prev =>
      prev.map(w =>
        w.id === workflowId
          ? {
              ...w,
              status: 'running' as const,
              startedAt: new Date().toISOString(),
              steps: w.steps.map((s, i) =>
                i === 0 ? { ...s, status: 'running' as const } : s
              ),
            }
          : w
      )
    )

    // Simulate workflow execution
    simulateWorkflow(workflowId)
  }

  const simulateWorkflow = (workflowId: string) => {
    let stepIndex = 0
    const interval = setInterval(() => {
      setWorkflows(prev => {
        const workflow = prev.find(w => w.id === workflowId)
        if (!workflow || workflow.status !== 'running') {
          clearInterval(interval)
          return prev
        }

        const updatedSteps = [...workflow.steps]
        if (stepIndex < updatedSteps.length) {
          if (stepIndex > 0) {
            updatedSteps[stepIndex - 1].status = 'completed'
            updatedSteps[stepIndex - 1].duration = Math.random() * 10 + 2
          }
          updatedSteps[stepIndex].status = 'running'
          stepIndex++
        } else {
          updatedSteps[updatedSteps.length - 1].status = 'completed'
          updatedSteps[updatedSteps.length - 1].duration = Math.random() * 10 + 2
          clearInterval(interval)
          return prev.map(w =>
            w.id === workflowId
              ? {
                  ...w,
                  status: 'completed' as const,
                  progress: 100,
                  steps: updatedSteps,
                  completedAt: new Date().toISOString(),
                }
              : w
          )
        }

        const progress = Math.round((stepIndex / updatedSteps.length) * 100)
        return prev.map(w =>
          w.id === workflowId ? { ...w, steps: updatedSteps, progress } : w
        )
      })
    }, 2000)
  }

  const handlePauseWorkflow = (workflowId: string) => {
    setWorkflows(prev =>
      prev.map(w =>
        w.id === workflowId ? { ...w, status: 'paused' as const } : w
      )
    )
  }

  const handleStopWorkflow = (workflowId: string) => {
    setWorkflows(prev =>
      prev.map(w =>
        w.id === workflowId
          ? {
              ...w,
              status: 'idle' as const,
              progress: 0,
              steps: w.steps.map(s => ({ ...s, status: 'pending' as const })),
            }
          : w
      )
    )
  }

  const handleCreateWorkflow = (templateIndex: number) => {
    const template = PREDEFINED_WORKFLOWS[templateIndex]
    const newWorkflow: Workflow = {
      id: Date.now().toString(),
      ...template,
      createdAt: new Date().toISOString(),
    }
    setWorkflows(prev => [...prev, newWorkflow])
    setSelectedWorkflow(newWorkflow.id)
    setShowCreateModal(false)
  }

  const handleDeleteWorkflow = (workflowId: string) => {
    setWorkflows(prev => prev.filter(w => w.id !== workflowId))
    if (selectedWorkflow === workflowId) {
      setSelectedWorkflow(workflows.length > 1 ? workflows[0].id : null)
    }
  }

  const currentWorkflow = workflows.find(w => w.id === selectedWorkflow)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <PlayCircle className="w-7 h-7 text-indigo-500" />
            Workflow Manager
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            End-to-end mission pipeline orchestration
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
        >
          <Plus className="w-5 h-5" />
          New Workflow
        </button>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Workflow List */}
        <div className="col-span-1 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Workflows ({workflows.length})
            </h3>
          </div>
          <div className="divide-y divide-gray-200 dark:divide-gray-700 max-h-96 overflow-y-auto">
            {workflows.map(workflow => (
              <div
                key={workflow.id}
                onClick={() => setSelectedWorkflow(workflow.id)}
                className={`p-4 cursor-pointer transition-colors ${
                  selectedWorkflow === workflow.id
                    ? 'bg-indigo-50 dark:bg-indigo-900/20'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(workflow.status)}
                    <span className="font-medium text-gray-900 dark:text-white text-sm">
                      {workflow.name}
                    </span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
                {workflow.status === 'running' && (
                  <div className="mt-2">
                    <div className="bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                      <div
                        className="bg-indigo-600 h-1.5 rounded-full transition-all"
                        style={{ width: `${workflow.progress}%` }}
                      />
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {workflow.progress}% complete
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Workflow Details */}
        <div className="col-span-2 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          {currentWorkflow ? (
            <>
              <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white">
                    {currentWorkflow.name}
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {currentWorkflow.description}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {currentWorkflow.status === 'idle' && (
                    <button
                      onClick={() => handleStartWorkflow(currentWorkflow.id)}
                      className="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-sm flex items-center gap-1"
                    >
                      <PlayCircle className="w-4 h-4" />
                      Start
                    </button>
                  )}
                  {currentWorkflow.status === 'running' && (
                    <>
                      <button
                        onClick={() => handlePauseWorkflow(currentWorkflow.id)}
                        className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 text-white rounded text-sm flex items-center gap-1"
                      >
                        <Pause className="w-4 h-4" />
                        Pause
                      </button>
                      <button
                        onClick={() => handleStopWorkflow(currentWorkflow.id)}
                        className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-sm flex items-center gap-1"
                      >
                        <Square className="w-4 h-4" />
                        Stop
                      </button>
                    </>
                  )}
                  {currentWorkflow.status === 'paused' && (
                    <button
                      onClick={() => handleStartWorkflow(currentWorkflow.id)}
                      className="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-sm flex items-center gap-1"
                    >
                      <PlayCircle className="w-4 h-4" />
                      Resume
                    </button>
                  )}
                  {currentWorkflow.status === 'completed' && (
                    <button
                      onClick={() => handleStopWorkflow(currentWorkflow.id)}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm flex items-center gap-1"
                    >
                      <RefreshCw className="w-4 h-4" />
                      Reset
                    </button>
                  )}
                  <button
                    onClick={() => handleDeleteWorkflow(currentWorkflow.id)}
                    className="px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white rounded text-sm flex items-center gap-1"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Progress Bar */}
              {currentWorkflow.status !== 'idle' && (
                <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 border-b border-gray-200 dark:border-gray-700">
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-gray-600 dark:text-gray-400">Progress</span>
                    <span className="font-medium text-gray-900 dark:text-white">
                      {currentWorkflow.progress}%
                    </span>
                  </div>
                  <div className="bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all"
                      style={{ width: `${currentWorkflow.progress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Steps */}
              <div className="p-4 space-y-3">
                {currentWorkflow.steps.map((step, index) => (
                  <div
                    key={step.id}
                    className={`flex items-center gap-4 p-3 rounded-lg border ${
                      step.status === 'running'
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                        : step.status === 'completed'
                        ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                        : step.status === 'failed'
                        ? 'border-red-500 bg-red-50 dark:bg-red-900/20'
                        : 'border-gray-200 dark:border-gray-700'
                    }`}
                  >
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 font-medium text-sm">
                      {index + 1}
                    </div>
                    {getStatusIcon(step.status)}
                    <div className="flex-1">
                      <div className="font-medium text-gray-900 dark:text-white text-sm">
                        {step.name}
                      </div>
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${getStepTypeColor(
                          step.type
                        )}`}
                      >
                        {step.type}
                      </span>
                    </div>
                    {step.duration && (
                      <div className="text-sm text-gray-500 dark:text-gray-400">
                        {step.duration.toFixed(1)}s
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="p-8 text-center text-gray-500 dark:text-gray-400">
              Select a workflow or create a new one
            </div>
          )}
        </div>
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-lg">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Create New Workflow
            </h3>
            <div className="space-y-3">
              {PREDEFINED_WORKFLOWS.map((template, index) => (
                <button
                  key={index}
                  onClick={() => handleCreateWorkflow(index)}
                  className="w-full p-4 text-left border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <div className="font-medium text-gray-900 dark:text-white">
                    {template.name}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {template.description}
                  </div>
                  <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {template.steps.length} steps
                  </div>
                </button>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default WorkflowPanel
