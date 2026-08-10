import axios from 'axios'
import { getSession } from 'next-auth/react'

// API Gateway URL - connects to microservices via gRPC
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:18000'
const OPS_API_URL = process.env.NEXT_PUBLIC_OPS_API_URL || 'http://localhost:18000'

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 second timeout
})

// Add auth token to requests
apiClient.interceptors.request.use(async (config) => {
  const session = await getSession()

  // Only add auth token if session exists
  // Production mode requires proper authentication
  if (session?.accessToken) {
    config.headers.Authorization = `Bearer ${session.accessToken}`
  } else if (process.env.NODE_ENV === 'development') {
    // In development, allow unauthenticated requests
    // The API will handle authentication based on AUTH_ENABLED setting
    console.warn('No session found. Requests may require authentication.')
  }

  return config
})

// Handle responses and errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized access
      window.location.href = '/auth/signin'
    }
    return Promise.reject(error)
  }
)

// API functions for microservices
export const api = {
  // Auth
  login: (credentials: { username: string; password: string }) =>
    apiClient.post('/auth/token', credentials),

  register: (userData: { username: string; email: string; password: string }) =>
    apiClient.post('/auth/register', userData),

  getCurrentUser: () => apiClient.get('/auth/me'),

  // Data Service - Telemetry
  ingestTelemetry: (data: {
    satellite_id: string
    timestamp?: string
    location: { latitude: number; longitude: number; altitude: number }
    temperature?: number
    battery_level?: number
  }) =>
    apiClient.post('/api/v1/data/telemetry', data),

  queryTelemetry: (params: {
    satellite_ids: string[]
    start_time: string
    end_time: string
    page?: number
    page_size?: number
  }) =>
    apiClient.get('/api/v1/data/telemetry', { params }),

  // Data Service - Gravity
  ingestGravity: (measurements: any[]) =>
    apiClient.post('/api/v1/data/gravity', { measurements }),

  queryGravity: (params: {
    satellite_ids?: string[]
    start_time?: string
    end_time?: string
    min_latitude?: number
    max_latitude?: number
    min_longitude?: number
    max_longitude?: number
    page?: number
    page_size?: number
  }) =>
    apiClient.get('/api/v1/data/gravity', { params }),

  exportData: (params: {
    export_type: 'telemetry' | 'gravity'
    satellite_ids?: string[]
    start_time?: string
    end_time?: string
    format: 'csv' | 'netcdf' | 'parquet'
  }) =>
    apiClient.post('/api/v1/data/export', params),

  // ML Service
  trainModel: (data: {
    model_name: string
    model_type: string
    dataset_id: string
    num_epochs?: number
    batch_size?: number
    learning_rate?: number
  }) =>
    apiClient.post('/api/v1/models/train', data),

  getTrainingStatus: (jobId: string) =>
    apiClient.get(`/api/v1/models/train/${jobId}`),

  listModels: (params?: {
    model_type?: string
    status?: string
    page?: number
    page_size?: number
  }) =>
    apiClient.get('/api/v1/models', { params }),

  predict: (modelId: string, data: {
    input_features: number[]
    options?: Record<string, string>
  }) =>
    apiClient.post(`/api/v1/models/${modelId}/predict`, data),

  deployModel: (modelId: string, data: {
    deployment_name: string
    num_replicas?: number
    instance_type?: string
  }) =>
    apiClient.post(`/api/v1/models/${modelId}/deploy`, data),

  deleteModel: (modelId: string) =>
    apiClient.delete(`/api/v1/models/${modelId}`),

  // Inversion Service
  startInversion: (data: {
    name: string
    description?: string
    measurement_ids: string[]
    parameters?: any
    grid?: any
  }) =>
    apiClient.post('/api/v1/inversions', data),

  getInversionStatus: (jobId: string) =>
    apiClient.get(`/api/v1/inversions/${jobId}`),

  listInversions: (params?: {
    status?: string
    start_time?: string
    end_time?: string
    page?: number
    page_size?: number
  }) =>
    apiClient.get('/api/v1/inversions', { params }),

  getInversionResults: (jobId: string, format?: string) =>
    apiClient.get(`/api/v1/inversions/${jobId}/results`, {
      params: { format },
      responseType: 'blob',
    }),

  cancelInversion: (jobId: string) =>
    apiClient.delete(`/api/v1/inversions/${jobId}`),

  // Satellite Control Service
  listSatellites: (status?: string) =>
    apiClient.get('/api/v1/satellites', {
      params: { status },
    }),

  getSatelliteStatus: (satelliteId: string) =>
    apiClient.get(`/api/v1/satellites/${satelliteId}`),

  sendCommand: (satelliteId: string, data: {
    command_type: string
    parameters?: Record<string, string>
    priority?: number
    wait_for_ack?: boolean
  }) =>
    apiClient.post(`/api/v1/satellites/${satelliteId}/commands`, data),

  getCommandStatus: (commandId: string) =>
    apiClient.get(`/api/v1/commands/${commandId}`),

  getOrbitPrediction: (satelliteId: string, params: {
    start_time: string
    end_time: string
    time_step_seconds?: number
  }) =>
    apiClient.get(`/api/v1/satellites/${satelliteId}/orbit`, { params }),

  // Legacy endpoints for backward compatibility
  getJobs: (params?: { status?: string; limit?: number }) =>
    apiClient.get('/api/v1/inversions', { params }),

  getJob: (jobId: string) =>
    apiClient.get(`/api/v1/inversions/${jobId}`),

  cancelJob: (jobId: string) =>
    apiClient.delete(`/api/v1/inversions/${jobId}`),

  // Health
  healthCheck: () =>
    apiClient.get('/health'),

  // Workflows (real gateway workflow engine)
  triggerWorkflow: (eventType: string, data: Record<string, unknown>) =>
    apiClient.post('/api/v1/workflows/trigger', { event_type: eventType, data }),

  listWorkflows: () =>
    apiClient.get('/api/v1/workflows/workflows'),

  listWorkflowExecutions: () =>
    apiClient.get('/api/v1/workflows/executions'),
}

export default apiClient
