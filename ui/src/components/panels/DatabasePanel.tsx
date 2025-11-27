'use client'

/**
 * Database Panel Component
 *
 * Data persistence and management for mission data
 */

import React, { useState, useEffect } from 'react'
import { Database, HardDrive, Users, FileText, Clock, Trash2, Download, Upload, Search, RefreshCw, Server, Activity } from 'lucide-react'
import { api } from '@/lib/api-client-full'

interface TableStats {
  name: string
  rows: number
  size: string
  lastModified: string
}

interface Job {
  id: string
  type: string
  status: string
  created_at: string
  completed_at?: string
  metadata?: any
}

interface User {
  id: string
  username: string
  email: string
  role: string
  created_at: string
  last_login?: string
}

export function DatabasePanel() {
  const [activeTab, setActiveTab] = useState<'overview' | 'jobs' | 'users' | 'products'>('overview')
  const [isLoading, setIsLoading] = useState(false)
  const [jobs, setJobs] = useState<Job[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [searchQuery, setSearchQuery] = useState('')

  const [dbStats] = useState({
    totalSize: '2.4 GB',
    tables: 12,
    connections: 5,
    uptime: '7d 14h 32m',
  })

  const [tableStats] = useState<TableStats[]>([
    { name: 'jobs', rows: 1234, size: '45 MB', lastModified: '2 min ago' },
    { name: 'users', rows: 56, size: '2 MB', lastModified: '1 hour ago' },
    { name: 'products', rows: 892, size: '1.2 GB', lastModified: '15 min ago' },
    { name: 'gravity_models', rows: 45, size: '890 MB', lastModified: '3 hours ago' },
    { name: 'orbits', rows: 234, size: '120 MB', lastModified: '30 min ago' },
    { name: 'telemetry', rows: 45678, size: '156 MB', lastModified: '1 min ago' },
  ])

  useEffect(() => {
    fetchData()
  }, [activeTab])

  const fetchData = async () => {
    setIsLoading(true)
    try {
      if (activeTab === 'jobs') {
        const response = await api.database.listJobs({ limit: 50 })
        setJobs(response.data.jobs || [])
      } else if (activeTab === 'users') {
        const response = await api.database.listUsers({ limit: 50 })
        setUsers(response.data.users || [])
      }
    } catch (error) {
      // Use mock data if API fails
      if (activeTab === 'jobs') {
        setJobs([
          { id: '1', type: 'inversion', status: 'completed', created_at: '2024-01-15T10:30:00Z', completed_at: '2024-01-15T10:45:00Z' },
          { id: '2', type: 'simulation', status: 'running', created_at: '2024-01-15T11:00:00Z' },
          { id: '3', type: 'calibration', status: 'pending', created_at: '2024-01-15T11:15:00Z' },
        ])
      } else if (activeTab === 'users') {
        setUsers([
          { id: '1', username: 'admin', email: 'admin@galileo.space', role: 'admin', created_at: '2024-01-01T00:00:00Z', last_login: '2024-01-15T09:00:00Z' },
          { id: '2', username: 'operator', email: 'operator@galileo.space', role: 'operator', created_at: '2024-01-05T00:00:00Z', last_login: '2024-01-15T08:30:00Z' },
        ])
      }
    } finally {
      setIsLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
      case 'running':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'pending':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300'
      case 'failed':
        return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
    }
  }

  const getRoleColor = (role: string) => {
    switch (role.toLowerCase()) {
      case 'admin':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
      case 'operator':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'viewer':
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Database className="w-7 h-7 text-teal-500" />
            Database Manager
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            PostgreSQL data persistence and management
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-3">
            <HardDrive className="w-8 h-8 text-teal-500" />
            <div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {dbStats.totalSize}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Total Size</div>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-3">
            <FileText className="w-8 h-8 text-blue-500" />
            <div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {dbStats.tables}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Tables</div>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-3">
            <Server className="w-8 h-8 text-green-500" />
            <div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {dbStats.connections}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Connections</div>
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-3">
            <Activity className="w-8 h-8 text-purple-500" />
            <div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {dbStats.uptime}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Uptime</div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-4">
          {[
            { id: 'overview', label: 'Overview', icon: Database },
            { id: 'jobs', label: 'Jobs', icon: Clock },
            { id: 'users', label: 'Users', icon: Users },
            { id: 'products', label: 'Products', icon: FileText },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-teal-500 text-teal-600 dark:text-teal-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        {activeTab === 'overview' && (
          <div className="p-4">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Table Statistics</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Table Name
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Rows
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Size
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Last Modified
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tableStats.map((table, index) => (
                    <tr
                      key={table.name}
                      className={index < tableStats.length - 1 ? 'border-b border-gray-100 dark:border-gray-700/50' : ''}
                    >
                      <td className="py-3 px-4">
                        <span className="font-mono text-sm text-gray-900 dark:text-white">
                          {table.name}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right text-sm text-gray-600 dark:text-gray-400">
                        {table.rows.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right text-sm text-gray-600 dark:text-gray-400">
                        {table.size}
                      </td>
                      <td className="py-3 px-4 text-right text-sm text-gray-500 dark:text-gray-500">
                        {table.lastModified}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'jobs' && (
          <div>
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search jobs..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div className="flex gap-2">
                <button className="px-3 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm flex items-center gap-1">
                  <Download className="w-4 h-4" />
                  Export
                </button>
              </div>
            </div>
            <div className="divide-y divide-gray-200 dark:divide-gray-700 max-h-96 overflow-y-auto">
              {jobs.length === 0 ? (
                <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                  {isLoading ? 'Loading jobs...' : 'No jobs found'}
                </div>
              ) : (
                jobs.map(job => (
                  <div key={job.id} className="p-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <div className="flex items-center gap-4">
                      <div className="font-mono text-sm text-gray-600 dark:text-gray-400">
                        {job.id.slice(0, 8)}
                      </div>
                      <div>
                        <div className="font-medium text-gray-900 dark:text-white">
                          {job.type}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          Created: {new Date(job.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(job.status)}`}>
                        {job.status}
                      </span>
                      <button className="p-1 text-gray-400 hover:text-red-500">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'users' && (
          <div>
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search users..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <button className="px-3 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm flex items-center gap-1">
                <Users className="w-4 h-4" />
                Add User
              </button>
            </div>
            <div className="divide-y divide-gray-200 dark:divide-gray-700 max-h-96 overflow-y-auto">
              {users.length === 0 ? (
                <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                  {isLoading ? 'Loading users...' : 'No users found'}
                </div>
              ) : (
                users.map(user => (
                  <div key={user.id} className="p-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-full bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center">
                        <span className="text-teal-600 dark:text-teal-400 font-medium">
                          {user.username.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <div className="font-medium text-gray-900 dark:text-white">
                          {user.username}
                        </div>
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {user.email}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${getRoleColor(user.role)}`}>
                        {user.role}
                      </span>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {user.last_login ? `Last login: ${new Date(user.last_login).toLocaleDateString()}` : 'Never logged in'}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'products' && (
          <div className="p-8 text-center">
            <FileText className="w-16 h-16 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Data Products
            </h3>
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              View and manage mission data products including gravity models, orbit files, and analysis results.
            </p>
            <div className="flex justify-center gap-3">
              <button className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm flex items-center gap-2">
                <Upload className="w-4 h-4" />
                Upload Product
              </button>
              <button className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm flex items-center gap-2">
                <Download className="w-4 h-4" />
                Export All
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default DatabasePanel
