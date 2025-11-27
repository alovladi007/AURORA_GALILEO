/**
 * Trade Study Service Hook
 *
 * Provides React Query hooks for mission design trade studies
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client-full'
import toast from 'react-hot-toast'

export interface TradeStudyConfig {
  parameter_ranges: Record<string, [number, number]>
  n_samples: number
  objectives: string[]
  constraints?: Record<string, number>
}

export interface TradeStudyResult {
  parameter_values: Record<string, number[]>
  objective_values: Record<string, number[]>
  pareto_indices?: number[]
  optimal_point?: Record<string, number>
  sensitivity?: Record<string, number>
}

export interface ParetoPoint {
  parameters: Record<string, number>
  objectives: Record<string, number>
  dominated: boolean
}

export interface SensitivityResult {
  parameter: string
  sensitivity_index: number
  first_order: number
  total_order: number
}

export function useBaselineStudy() {
  const queryClient = useQueryClient()

  const runMutation = useMutation({
    mutationFn: async (params: {
      baseline_range: [number, number]  // km
      n_samples: number
      orbit_altitude: number            // km
      objectives: string[]
    }) => {
      const response = await api.tradeStudy.runBaselineStudy(params)
      return response.data as TradeStudyResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastBaselineStudy'], data)
      toast.success('Baseline trade study complete')
    },
    onError: (error: any) => {
      toast.error(`Baseline study failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    run: runMutation.mutate,
    runAsync: runMutation.mutateAsync,
    isLoading: runMutation.isPending,
    data: runMutation.data,
    error: runMutation.error,
    reset: runMutation.reset,
  }
}

export function useOrbitStudy() {
  const queryClient = useQueryClient()

  const runMutation = useMutation({
    mutationFn: async (params: {
      altitude_range: [number, number]     // km
      inclination_range: [number, number]  // degrees
      n_samples: number
      objectives: string[]
    }) => {
      const response = await api.tradeStudy.runOrbitStudy(params)
      return response.data as TradeStudyResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastOrbitStudy'], data)
      toast.success('Orbit trade study complete')
    },
    onError: (error: any) => {
      toast.error(`Orbit study failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    run: runMutation.mutate,
    runAsync: runMutation.mutateAsync,
    isLoading: runMutation.isPending,
    data: runMutation.data,
    error: runMutation.error,
    reset: runMutation.reset,
  }
}

export function useOpticalStudy() {
  const queryClient = useQueryClient()

  const runMutation = useMutation({
    mutationFn: async (params: {
      power_range: [number, number]      // Watts
      aperture_range: [number, number]   // meters
      n_samples: number
      objectives: string[]
    }) => {
      const response = await api.tradeStudy.runOpticalStudy(params)
      return response.data as TradeStudyResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastOpticalStudy'], data)
      toast.success('Optical trade study complete')
    },
    onError: (error: any) => {
      toast.error(`Optical study failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    run: runMutation.mutate,
    runAsync: runMutation.mutateAsync,
    isLoading: runMutation.isPending,
    data: runMutation.data,
    error: runMutation.error,
    reset: runMutation.reset,
  }
}

export function useParetoFront() {
  const queryClient = useQueryClient()

  const computeMutation = useMutation({
    mutationFn: async (params: {
      study_data: TradeStudyResult
      objectives: string[]
      minimize?: boolean[]
    }) => {
      const response = await api.tradeStudy.findParetoFront(params)
      return response.data as ParetoPoint[]
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastParetoFront'], data)
      toast.success('Pareto front computed')
    },
    onError: (error: any) => {
      toast.error(`Pareto computation failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    compute: computeMutation.mutate,
    computeAsync: computeMutation.mutateAsync,
    isLoading: computeMutation.isPending,
    data: computeMutation.data,
    error: computeMutation.error,
  }
}

export function useSensitivityAnalysis() {
  const queryClient = useQueryClient()

  const analyzeMutation = useMutation({
    mutationFn: async (params: {
      study_data: TradeStudyResult
      target_objective: string
      method?: 'sobol' | 'morris' | 'fast'
    }) => {
      const response = await api.tradeStudy.sensitivityAnalysis(params)
      return response.data as SensitivityResult[]
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastSensitivity'], data)
      toast.success('Sensitivity analysis complete')
    },
    onError: (error: any) => {
      toast.error(`Sensitivity analysis failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    analyze: analyzeMutation.mutate,
    analyzeAsync: analyzeMutation.mutateAsync,
    isLoading: analyzeMutation.isPending,
    data: analyzeMutation.data,
    error: analyzeMutation.error,
  }
}

export function useDesignComparison() {
  const compareMutation = useMutation({
    mutationFn: async (params: {
      designs: Record<string, any>[]
      metrics: string[]
    }) => {
      const response = await api.tradeStudy.compareDesigns(params)
      return response.data
    },
    onSuccess: () => {
      toast.success('Design comparison complete')
    },
    onError: (error: any) => {
      toast.error(`Comparison failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    compare: compareMutation.mutate,
    compareAsync: compareMutation.mutateAsync,
    isLoading: compareMutation.isPending,
    data: compareMutation.data,
    error: compareMutation.error,
  }
}

export function useLastTradeStudy(type: 'baseline' | 'orbit' | 'optical') {
  const keyMap = {
    baseline: 'lastBaselineStudy',
    orbit: 'lastOrbitStudy',
    optical: 'lastOpticalStudy',
  }

  return useQuery<TradeStudyResult | null>({
    queryKey: [keyMap[type]],
    queryFn: () => null,
    staleTime: Infinity,
  })
}

export function useLastParetoFront() {
  return useQuery<ParetoPoint[] | null>({
    queryKey: ['lastParetoFront'],
    queryFn: () => null,
    staleTime: Infinity,
  })
}
