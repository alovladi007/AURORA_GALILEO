/**
 * Simulation Service Hook
 *
 * Provides React Query hooks for orbit propagation and formation flying
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client-full'
import toast from 'react-hot-toast'

export interface OrbitalElements {
  semi_major_axis: number  // km
  eccentricity: number
  inclination: number      // degrees
  raan: number            // degrees
  argument_of_perigee: number  // degrees
  true_anomaly: number    // degrees
}

export interface PropagationResult {
  trajectory: number[][]  // [x, y, z, vx, vy, vz][]
  times: number[]
  orbital_parameters?: {
    period: number
    apogee: number
    perigee: number
    velocity_apogee: number
    velocity_perigee: number
  }
}

export interface FormationResult {
  relative_trajectory: number[][]
  times: number[]
  chief_trajectory: number[][]
  baselines: number[][]
}

export function useOrbitPropagation() {
  const queryClient = useQueryClient()

  const propagateMutation = useMutation({
    mutationFn: async (params: {
      orbital_elements: OrbitalElements
      duration: number
      time_step?: number
    }) => {
      const response = await api.simulation.propagateSingle({
        orbital_elements: params.orbital_elements,
        duration: params.duration,
        time_step: params.time_step || 60,
      })
      return response.data as PropagationResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastPropagation'], data)
      toast.success('Orbit propagation complete')
    },
    onError: (error: any) => {
      toast.error(`Propagation failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    propagate: propagateMutation.mutate,
    propagateAsync: propagateMutation.mutateAsync,
    isLoading: propagateMutation.isPending,
    data: propagateMutation.data,
    error: propagateMutation.error,
    reset: propagateMutation.reset,
  }
}

export function useFormationSimulation() {
  const queryClient = useQueryClient()

  const simulateMutation = useMutation({
    mutationFn: async (params: {
      chief_elements: OrbitalElements
      deputy_offsets: number[]  // [x, y, z, vx, vy, vz] in km and km/s
      duration: number
      time_step?: number
    }) => {
      const response = await api.simulation.propagateFormation({
        chief_elements: params.chief_elements,
        deputy_offsets: params.deputy_offsets,
        duration: params.duration,
        time_step: params.time_step || 60,
      })
      return response.data as FormationResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastFormation'], data)
      toast.success('Formation simulation complete')
    },
    onError: (error: any) => {
      toast.error(`Formation simulation failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    simulate: simulateMutation.mutate,
    simulateAsync: simulateMutation.mutateAsync,
    isLoading: simulateMutation.isPending,
    data: simulateMutation.data,
    error: simulateMutation.error,
    reset: simulateMutation.reset,
  }
}

export function useBaselineComputation() {
  const queryClient = useQueryClient()

  const computeMutation = useMutation({
    mutationFn: async (params: {
      chief_trajectory: number[][]
      deputy_trajectory: number[][]
      times: number[]
    }) => {
      const response = await api.simulation.computeBaselines(params)
      return response.data
    },
    onSuccess: () => {
      toast.success('Baseline computation complete')
    },
    onError: (error: any) => {
      toast.error(`Baseline computation failed: ${error.response?.data?.detail || error.message}`)
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

export function useLastPropagation() {
  return useQuery<PropagationResult | null>({
    queryKey: ['lastPropagation'],
    queryFn: () => null,
    staleTime: Infinity,
  })
}

export function useLastFormation() {
  return useQuery<FormationResult | null>({
    queryKey: ['lastFormation'],
    queryFn: () => null,
    staleTime: Infinity,
  })
}
