import axios from 'axios'
import { getSession } from 'next-auth/react'

// Use environment variable with correct default port for main API
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5050'
const OPS_API_URL = process.env.NEXT_PUBLIC_OPS_API_URL || 'http://localhost:8000'

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
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

// API functions
export const api = {
  // Auth
  login: (credentials: { username: string; password: string }) =>
    apiClient.post('/auth/token', credentials),
  
  register: (userData: { username: string; email: string; password: string }) =>
    apiClient.post('/auth/register', userData),
  
  getCurrentUser: () => apiClient.get('/auth/me'),
  
  // Jobs
  getJobs: (params?: { status?: string; limit?: number }) =>
    apiClient.get('/ops/jobs', { params }),
  
  getJob: (jobId: string) =>
    apiClient.get(`/ops/jobs/${jobId}`),
  
  createPlan: (data: any) =>
    apiClient.post('/ops/plan', data),
  
  createIngest: (data: any) =>
    apiClient.post('/ops/ingest', data),
  
  createProcess: (data: any) =>
    apiClient.post('/ops/process', data),
  
  createCatalog: (data: any) =>
    apiClient.post('/ops/catalog', data),
  
  cancelJob: (jobId: string) =>
    apiClient.delete(`/ops/jobs/${jobId}`),
  
  // Health
  healthCheck: () =>
    apiClient.get('/health'),
}

export default apiClient
