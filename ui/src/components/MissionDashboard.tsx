'use client'

/**
 * Mission Control Dashboard
 *
 * Unified control panel for GALILEO Platform operations.
 * Geospatial Analytics, Learning, and Intelligence for Land, Environment & Oceanography
 * Integrates all 11 services for comprehensive mission management.
 */

import React, { useState, useEffect } from 'react'
import {
  Activity, Satellite, Zap, Database, Settings,
  PlayCircle, BarChart3, Shield, Cpu, RefreshCw, TrendingUp
} from 'lucide-react'
import { JobConsole } from './JobConsole'
import { api } from '@/lib/api-client'
import toast from 'react-hot-toast'

// Import panel components
import {
  SimulationPanel,
  InversionPanel,
  MLPanel,
  ControlPanel,
  EmulatorPanel,
  TradeStudyPanel,
  TasksPanel,
  WorkflowPanel,
  DatabasePanel
} from './panels'

interface DashboardProps {
  className?: string
}

type ServicePanel =
  | 'jobs'
  | 'simulation'
  | 'inversion'
  | 'control'
  | 'emulator'
  | 'ml'
  | 'workflow'
  | 'tasks'
  | 'trade-study'
  | 'database'

export function MissionDashboard({ className = '' }: DashboardProps) {
  const [activePanel, setActivePanel] = useState<ServicePanel>('jobs')
  const [systemStatus, setSystemStatus] = useState({
    api: 'unknown',
    database: 'unknown',
    celery: 'unknown',
    minio: 'unknown'
  })
  const [loading, setLoading] = useState(false)

  // Check system health on mount
  useEffect(() => {
    checkSystemHealth()
    const interval = setInterval(checkSystemHealth, 30000) // Check every 30 seconds
    return () => clearInterval(interval)
  }, [])

  const checkSystemHealth = async () => {
    try {
      const response = await api.healthCheck()
      const health = response.data

      setSystemStatus({
        api: health.status === 'healthy' || health.database ? 'healthy' : 'unhealthy',
        database: health.database ? 'healthy' : 'unhealthy',
        celery: health.celery ? 'healthy' : 'unhealthy',
        minio: health.minio ? 'healthy' : 'unhealthy'
      })
    } catch (error) {
      setSystemStatus({
        api: 'unhealthy',
        database: 'unknown',
        celery: 'unknown',
        minio: 'unknown'
      })
    }
  }

  const services = [
    {
      id: 'jobs' as ServicePanel,
      name: 'Job Console',
      icon: Activity,
      color: 'blue',
      description: 'Active processing jobs & history',
      showComponent: true
    },
    {
      id: 'simulation' as ServicePanel,
      name: 'Simulation',
      icon: Satellite,
      color: 'blue',
      description: 'Orbit propagation & measurements',
      showComponent: true
    },
    {
      id: 'inversion' as ServicePanel,
      name: 'Inversion',
      icon: BarChart3,
      color: 'green',
      description: 'Gravity field estimation',
      showComponent: true
    },
    {
      id: 'control' as ServicePanel,
      name: 'Control',
      icon: Settings,
      color: 'purple',
      description: 'Formation control & maneuvers',
      showComponent: true
    },
    {
      id: 'emulator' as ServicePanel,
      name: 'Emulator',
      icon: Activity,
      color: 'orange',
      description: 'Real-time signal emulation',
      showComponent: true
    },
    {
      id: 'ml' as ServicePanel,
      name: 'ML',
      icon: Cpu,
      color: 'pink',
      description: 'PINN & U-Net training',
      showComponent: true
    },
    {
      id: 'trade-study' as ServicePanel,
      name: 'Trade Study',
      icon: TrendingUp,
      color: 'cyan',
      description: 'Pareto analysis & optimization',
      showComponent: true
    },
    {
      id: 'tasks' as ServicePanel,
      name: 'Tasks',
      icon: Zap,
      color: 'yellow',
      description: 'Celery task queue',
      showComponent: true
    },
    {
      id: 'workflow' as ServicePanel,
      name: 'Workflows',
      icon: PlayCircle,
      color: 'indigo',
      description: 'End-to-end pipelines',
      showComponent: true
    },
    {
      id: 'database' as ServicePanel,
      name: 'Database',
      icon: Database,
      color: 'teal',
      description: 'Data persistence',
      showComponent: true
    },
  ]

  const handleCreateJob = async (type: 'plan' | 'ingest' | 'process' | 'catalog') => {
    setLoading(true)
    try {
      // Trigger the real gateway workflow engine; each job type maps
      // to a workflow event type.
      const eventTypeMap = {
        plan: 'mission.plan.requested',
        ingest: 'data.ingest.requested',
        process: 'processing.requested',
        catalog: 'catalog.update.requested',
      } as const

      await api.triggerWorkflow(eventTypeMap[type], {
        config: { algorithm: 'variational', degree_max: 60 },
        requested_at: new Date().toISOString(),
      })

      toast.success(`${type.toUpperCase()} workflow triggered`)
    } catch (error: any) {
      toast.error(`Failed to create ${type} job: ${error.response?.data?.detail || error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const renderServiceContent = () => {
    const service = services.find(s => s.id === activePanel)

    // Render actual panel components based on active panel
    switch (activePanel) {
      case 'jobs':
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Job Console
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  Monitor and manage processing jobs
                </p>
              </div>
              <button
                onClick={checkSystemHealth}
                className="p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
                title="Refresh system status"
              >
                <RefreshCw className="w-5 h-5" />
              </button>
            </div>

            <JobConsole />

            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Create New Job
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <button
                  onClick={() => handleCreateJob('plan')}
                  disabled={loading}
                  className="px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div className="text-sm font-medium">Mission Plan</div>
                  <div className="text-xs opacity-75 mt-1">Orbit design</div>
                </button>
                <button
                  onClick={() => handleCreateJob('ingest')}
                  disabled={loading}
                  className="px-4 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div className="text-sm font-medium">Data Ingest</div>
                  <div className="text-xs opacity-75 mt-1">Import data</div>
                </button>
                <button
                  onClick={() => handleCreateJob('process')}
                  disabled={loading}
                  className="px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div className="text-sm font-medium">Process</div>
                  <div className="text-xs opacity-75 mt-1">Run analysis</div>
                </button>
                <button
                  onClick={() => handleCreateJob('catalog')}
                  disabled={loading}
                  className="px-4 py-3 bg-orange-600 hover:bg-orange-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div className="text-sm font-medium">Catalog</div>
                  <div className="text-xs opacity-75 mt-1">List products</div>
                </button>
              </div>
            </div>
          </div>
        )

      case 'simulation':
        return <SimulationPanel />

      case 'inversion':
        return <InversionPanel />

      case 'control':
        return <ControlPanel />

      case 'emulator':
        return <EmulatorPanel />

      case 'ml':
        return <MLPanel />

      case 'trade-study':
        return <TradeStudyPanel />

      case 'tasks':
        return <TasksPanel />

      case 'workflow':
        return <WorkflowPanel />

      case 'database':
        return <DatabasePanel />

      default:
        // Fallback for panels not yet implemented (workflow, database)
        return (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              {service?.name} Service
            </h2>

            <div className="text-gray-600 dark:text-gray-400">
              <p className="mb-4">
                {service?.description}
              </p>

              <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <div className="flex items-start gap-3">
                  <Shield className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <div className="font-medium text-blue-900 dark:text-blue-100">
                      Service Coming Soon
                    </div>
                    <div className="text-sm text-blue-700 dark:text-blue-300 mt-1">
                      This service panel is under development. Use the Job Console to create and monitor processing tasks.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )
    }
  }

  const getColorClass = (color: string, type: 'bg' | 'text' | 'border') => {
    const colors: Record<string, Record<string, string>> = {
      blue: { bg: 'bg-blue-500', text: 'text-blue-500', border: 'border-blue-500' },
      green: { bg: 'bg-green-500', text: 'text-green-500', border: 'border-green-500' },
      purple: { bg: 'bg-purple-500', text: 'text-purple-500', border: 'border-purple-500' },
      orange: { bg: 'bg-orange-500', text: 'text-orange-500', border: 'border-orange-500' },
      pink: { bg: 'bg-pink-500', text: 'text-pink-500', border: 'border-pink-500' },
      indigo: { bg: 'bg-indigo-500', text: 'text-indigo-500', border: 'border-indigo-500' },
      yellow: { bg: 'bg-yellow-500', text: 'text-yellow-500', border: 'border-yellow-500' },
      teal: { bg: 'bg-teal-500', text: 'text-teal-500', border: 'border-teal-500' },
      cyan: { bg: 'bg-cyan-500', text: 'text-cyan-500', border: 'border-cyan-500' },
    }
    return colors[color]?.[type] || ''
  }

  return (
    <div className={`min-h-screen bg-gray-50 dark:bg-gray-900 ${className}`}>
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                GALILEO Mission Control
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Geospatial Analytics, Learning, and Intelligence for Land, Environment & Oceanography
              </p>
            </div>

            {/* System Status */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${systemStatus.api === 'healthy' ? 'bg-green-500' : systemStatus.api === 'unhealthy' ? 'bg-red-500' : 'bg-yellow-500 animate-pulse'}`} />
                <span className="text-sm text-gray-600 dark:text-gray-300">API</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${systemStatus.database === 'healthy' ? 'bg-green-500' : systemStatus.database === 'unhealthy' ? 'bg-red-500' : 'bg-yellow-500 animate-pulse'}`} />
                <span className="text-sm text-gray-600 dark:text-gray-300">Database</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${systemStatus.celery === 'healthy' ? 'bg-green-500' : systemStatus.celery === 'unhealthy' ? 'bg-red-500' : 'bg-yellow-500 animate-pulse'}`} />
                <span className="text-sm text-gray-600 dark:text-gray-300">Workers</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="flex h-[calc(100vh-80px)]">
        {/* Sidebar */}
        <aside className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 overflow-y-auto">
          <nav className="p-4 space-y-2">
            {services.map((service) => {
              const Icon = service.icon
              const isActive = activePanel === service.id

              return (
                <button
                  key={service.id}
                  onClick={() => setActivePanel(service.id)}
                  className={`
                    w-full flex items-start gap-3 p-3 rounded-lg transition-colors
                    ${isActive
                      ? 'bg-gray-100 dark:bg-gray-700 border-l-4 ' + getColorClass(service.color, 'border')
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    }
                  `}
                >
                  <Icon
                    className={`w-5 h-5 mt-0.5 flex-shrink-0 ${isActive ? getColorClass(service.color, 'text') : 'text-gray-400'}`}
                  />
                  <div className="flex-1 text-left">
                    <div className={`font-medium ${isActive ? 'text-gray-900 dark:text-white' : 'text-gray-700 dark:text-gray-300'}`}>
                      {service.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      {service.description}
                    </div>
                  </div>
                </button>
              )
            })}
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900">
          <div className="p-6">
            {renderServiceContent()}
          </div>
        </main>
      </div>
    </div>
  )
}

export default MissionDashboard
