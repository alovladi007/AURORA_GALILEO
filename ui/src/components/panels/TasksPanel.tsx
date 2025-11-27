'use client'

/**
 * Tasks Panel Component
 *
 * Enhanced task management with Celery integration
 */

import React, { useState } from 'react'
import { Zap, Play, RotateCcw, X, RefreshCw, Server, Clock, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import {
  useActiveTasks, useScheduledTasks, useWorkerStats,
  useSubmitTask, useCancelTask, useRetryTask, Task, WorkerInfo
} from '@/hooks/useTasks'

export function TasksPanel() {
  const [showSubmitModal, setShowSubmitModal] = useState(false)
  const [selectedTaskType, setSelectedTaskType] = useState('simulation.propagate_orbit')
  const [taskParams, setTaskParams] = useState('{}')

  const { data: activeTasks, isLoading: isLoadingActive } = useActiveTasks()
  const { data: scheduledTasks, isLoading: isLoadingScheduled } = useScheduledTasks()
  const { data: workers, isLoading: isLoadingWorkers } = useWorkerStats()
  const { submit, isLoading: isSubmitting } = useSubmitTask()
  const { cancel, isLoading: isCancelling } = useCancelTask()
  const { retry, isLoading: isRetrying } = useRetryTask()

  const handleSubmitTask = () => {
    try {
      const params = JSON.parse(taskParams)
      submit({
        task_name: selectedTaskType,
        parameters: params,
        priority: 5,
      })
      setShowSubmitModal(false)
      setTaskParams('{}')
    } catch (e) {
      // Invalid JSON
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status.toUpperCase()) {
      case 'PENDING':
        return <Clock className="w-5 h-5 text-yellow-500" />
      case 'STARTED':
        return <RotateCcw className="w-5 h-5 text-blue-500 animate-spin" />
      case 'SUCCESS':
        return <CheckCircle className="w-5 h-5 text-green-500" />
      case 'FAILURE':
        return <XCircle className="w-5 h-5 text-red-500" />
      case 'REVOKED':
        return <X className="w-5 h-5 text-gray-500" />
      default:
        return <AlertTriangle className="w-5 h-5 text-gray-400" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status.toUpperCase()) {
      case 'PENDING':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300'
      case 'STARTED':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'SUCCESS':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
      case 'FAILURE':
        return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
    }
  }

  const isLoading = isLoadingActive || isLoadingScheduled || isLoadingWorkers

  const taskTypes = [
    { value: 'simulation.propagate_orbit', label: 'Propagate Orbit' },
    { value: 'simulation.propagate_formation', label: 'Formation Simulation' },
    { value: 'inversion.tikhonov_solve', label: 'Tikhonov Inversion' },
    { value: 'inversion.joint_inversion_run', label: 'Joint Inversion' },
    { value: 'ml.train_pinn', label: 'Train PINN' },
    { value: 'ml.train_unet', label: 'Train U-Net' },
    { value: 'calibration.analyze_phase_noise', label: 'Phase Noise Analysis' },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Zap className="w-7 h-7 text-yellow-500" />
            Task Queue
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Celery background task management
          </p>
        </div>
        <button
          onClick={() => setShowSubmitModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors"
        >
          <Play className="w-5 h-5" />
          Submit Task
        </button>
      </div>

      {/* Worker Stats */}
      <div className="grid grid-cols-4 gap-4">
        {workers?.map((worker) => (
          <div
            key={worker.name}
            className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
          >
            <div className="flex items-center gap-3 mb-3">
              <Server className={`w-5 h-5 ${worker.status === 'online' ? 'text-green-500' : 'text-red-500'}`} />
              <div>
                <div className="font-medium text-gray-900 dark:text-white text-sm">
                  {worker.name.split('@')[1] || 'Worker'}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {worker.pool} pool
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div className="text-gray-500 dark:text-gray-400">Active</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">
                  {worker.active_tasks}
                </div>
              </div>
              <div>
                <div className="text-gray-500 dark:text-gray-400">Capacity</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">
                  {worker.max_concurrency}
                </div>
              </div>
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Uptime: {Math.floor((worker.uptime || 0) / 60)} min
            </div>
          </div>
        )) || (
          <div className="col-span-4 text-center py-8 text-gray-500 dark:text-gray-400">
            No workers connected
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Active Tasks */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <RotateCcw className="w-5 h-5 text-blue-500" />
              Active Tasks ({activeTasks?.length || 0})
            </h3>
          </div>
          <div className="divide-y divide-gray-200 dark:divide-gray-700 max-h-96 overflow-y-auto">
            {activeTasks?.length === 0 ? (
              <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                No active tasks
              </div>
            ) : (
              activeTasks?.map((task) => (
                <div key={task.task_id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <div className="flex items-start gap-3">
                    {getStatusIcon(task.status)}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-gray-900 dark:text-white truncate">
                        {task.task_name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        ID: {task.task_id.slice(0, 12)}...
                      </div>
                      {task.worker && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          Worker: {task.worker.split('@')[1]}
                        </div>
                      )}
                      {task.progress !== undefined && (
                        <div className="mt-2">
                          <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                            <span>Progress</span>
                            <span>{task.progress}%</span>
                          </div>
                          <div className="bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                            <div
                              className="bg-blue-600 h-1.5 rounded-full transition-all"
                              style={{ width: `${task.progress}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => cancel(task.task_id)}
                      disabled={isCancelling}
                      className="px-2 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700 transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Scheduled Tasks */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-orange-500" />
              Scheduled Tasks ({scheduledTasks?.length || 0})
            </h3>
          </div>
          <div className="divide-y divide-gray-200 dark:divide-gray-700 max-h-96 overflow-y-auto">
            {scheduledTasks?.length === 0 ? (
              <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                No scheduled tasks
              </div>
            ) : (
              scheduledTasks?.map((task) => (
                <div key={task.task_id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <div className="flex items-start gap-3">
                    <Clock className="w-5 h-5 text-orange-500" />
                    <div className="flex-1">
                      <div className="font-medium text-gray-900 dark:text-white">
                        {task.task_name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        ID: {task.task_id.slice(0, 12)}...
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Quick Submit Buttons */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Quick Submit</h3>
        <div className="grid grid-cols-4 gap-3">
          <button
            onClick={() => submit({ task_name: 'simulation.propagate_orbit', parameters: { duration: 5400 }, priority: 5 })}
            className="px-3 py-2 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors text-sm"
          >
            Orbit Propagation
          </button>
          <button
            onClick={() => submit({ task_name: 'inversion.tikhonov_solve', parameters: { degree_max: 60 }, priority: 5 })}
            className="px-3 py-2 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 rounded hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors text-sm"
          >
            Inversion
          </button>
          <button
            onClick={() => submit({ task_name: 'ml.train_pinn', parameters: { epochs: 100 }, priority: 5 })}
            className="px-3 py-2 bg-pink-50 dark:bg-pink-900/20 text-pink-700 dark:text-pink-300 rounded hover:bg-pink-100 dark:hover:bg-pink-900/30 transition-colors text-sm"
          >
            PINN Training
          </button>
          <button
            onClick={() => submit({ task_name: 'calibration.analyze_phase_noise', parameters: {}, priority: 5 })}
            className="px-3 py-2 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 rounded hover:bg-purple-100 dark:hover:bg-purple-900/30 transition-colors text-sm"
          >
            Calibration
          </button>
        </div>
      </div>

      {/* Submit Modal */}
      {showSubmitModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Submit Task
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Task Type
                </label>
                <select
                  value={selectedTaskType}
                  onChange={(e) => setSelectedTaskType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {taskTypes.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Parameters (JSON)
                </label>
                <textarea
                  value={taskParams}
                  onChange={(e) => setTaskParams(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm"
                  placeholder='{"key": "value"}'
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowSubmitModal(false)}
                className="flex-1 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitTask}
                disabled={isSubmitting}
                className="flex-1 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {isSubmitting ? 'Submitting...' : 'Submit'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default TasksPanel
