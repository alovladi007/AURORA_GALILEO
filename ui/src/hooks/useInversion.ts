/**
 * Inversion Service Hook
 *
 * Provides React Query hooks for gravity field inversion operations
 * Updated for microservices architecture
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import toast from 'react-hot-toast'

export interface InversionConfig {
  algorithm: 'tikhonov' | 'variational' | 'mascon' | 'spherical_harmonic'
  degree_max: number
  regularization_parameter?: number
  max_iterations?: number
}

export interface InversionResult {
  coefficients?: number[][]
  residuals?: number[]
  convergence?: {
    iterations: number
    final_residual: number
    converged: boolean
  }
  gravity_grid?: {
    latitudes: number[]
    longitudes: number[]
    values: number[][]
  }
  statistics?: {
    mean: number
    std: number
    min: number
    max: number
  }
}

export interface GravityGridResult {
  latitudes: number[]
  longitudes: number[]
  values: number[][]  // [lat][lon]
  statistics: {
    mean: number
    std: number
    min: number
    max: number
  }
}

export function useGravityEstimation() {
  const queryClient = useQueryClient()

  const estimateMutation = useMutation({
    mutationFn: async (params: {
      observations: number[][]  // [range, phase, lat, lon, alt][]
      config: InversionConfig
    }) => {
      const response = await api.inversion.estimateGravity(params)
      return response.data as InversionResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastInversion'], data)
      toast.success('Gravity estimation complete')
    },
    onError: (error: any) => {
      toast.error(`Inversion failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    estimate: estimateMutation.mutate,
    estimateAsync: estimateMutation.mutateAsync,
    isLoading: estimateMutation.isPending,
    data: estimateMutation.data,
    error: estimateMutation.error,
    reset: estimateMutation.reset,
  }
}

export function useTikhonovInversion() {
  const queryClient = useQueryClient()

  const solveMutation = useMutation({
    mutationFn: async (params: {
      design_matrix: number[][]
      observations: number[]
      regularization_param: number
      method?: 'svd' | 'lsqr' | 'cholesky'
    }) => {
      const response = await api.inversion.solveVariational(params)
      return response.data
    },
    onSuccess: () => {
      toast.success('Tikhonov inversion complete')
    },
    onError: (error: any) => {
      toast.error(`Tikhonov inversion failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    solve: solveMutation.mutate,
    solveAsync: solveMutation.mutateAsync,
    isLoading: solveMutation.isPending,
    data: solveMutation.data,
    error: solveMutation.error,
  }
}

export function useGravityGrid() {
  const queryClient = useQueryClient()

  const gridMutation = useMutation({
    mutationFn: async (params: {
      coefficients: number[][]
      lat_range: [number, number]
      lon_range: [number, number]
      resolution: number
    }) => {
      const response = await api.inversion.gridField(params)
      return response.data as GravityGridResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastGravityGrid'], data)
      toast.success('Gravity grid computed')
    },
    onError: (error: any) => {
      toast.error(`Grid computation failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    computeGrid: gridMutation.mutate,
    computeGridAsync: gridMutation.mutateAsync,
    isLoading: gridMutation.isPending,
    data: gridMutation.data,
    error: gridMutation.error,
  }
}

export function useLastInversion() {
  return useQuery<InversionResult | null>({
    queryKey: ['lastInversion'],
    queryFn: () => null,
    staleTime: Infinity,
  })
}

export function useLastGravityGrid() {
  return useQuery<GravityGridResult | null>({
    queryKey: ['lastGravityGrid'],
    queryFn: () => null,
    staleTime: Infinity,
  })
}

// New microservices-based hooks

export function useInversionJobs(params?: {
  status?: string
  start_time?: string
  end_time?: string
}) {
  return useQuery({
    queryKey: ['inversions', params],
    queryFn: async () => {
      const response = await api.listInversions(params)
      return response.data
    },
    refetchInterval: 5000, // Poll every 5 seconds
  })
}

export function useInversionJob(jobId: string | null) {
  return useQuery({
    queryKey: ['inversion', jobId],
    queryFn: async () => {
      if (!jobId) return null
      const response = await api.getInversionStatus(jobId)
      return response.data
    },
    enabled: !!jobId,
    refetchInterval: (data) => {
      // Poll more frequently if job is running
      if (data?.status === 'running') return 2000
      if (data?.status === 'queued') return 5000
      return false // Stop polling if completed/failed
    },
  })
}

export function useStartInversion() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: {
      name: string
      description?: string
      measurement_ids: string[]
      parameters?: any
      grid?: any
    }) => {
      const response = await api.startInversion(data)
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['inversions'] })
      toast.success(`Inversion job started: ${data.job_id}`)
    },
    onError: (error: any) => {
      toast.error(`Failed to start inversion: ${error.response?.data?.detail || error.message}`)
    },
  })
}

export function useCancelInversion() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (jobId: string) => {
      const response = await api.cancelInversion(jobId)
      return response.data
    },
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['inversions'] })
      queryClient.invalidateQueries({ queryKey: ['inversion', jobId] })
      toast.success('Inversion cancelled')
    },
    onError: (error: any) => {
      toast.error(`Failed to cancel: ${error.response?.data?.detail || error.message}`)
    },
  })
}

export function useDownloadInversionResults() {
  return useMutation({
    mutationFn: async (params: { jobId: string; format?: string }) => {
      const response = await api.getInversionResults(params.jobId, params.format)
      return response.data
    },
    onSuccess: (blob, params) => {
      // Create download link
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `inversion_${params.jobId}.${params.format || 'netcdf'}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success('Results downloaded')
    },
    onError: (error: any) => {
      toast.error(`Download failed: ${error.response?.data?.detail || error.message}`)
    },
  })
}
