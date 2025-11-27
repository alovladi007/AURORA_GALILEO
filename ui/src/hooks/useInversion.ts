/**
 * Inversion Service Hook
 *
 * Provides React Query hooks for gravity field inversion operations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client-full'
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
