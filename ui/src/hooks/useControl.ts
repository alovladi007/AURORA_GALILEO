/**
 * Control Service Hook
 *
 * Provides React Query hooks for formation control and GNC operations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client-full'
import toast from 'react-hot-toast'

export interface LQRConfig {
  Q_position: number[]  // Position weight [x, y, z]
  Q_velocity: number[]  // Velocity weight [vx, vy, vz]
  R_control: number[]   // Control weight [ux, uy, uz]
}

export interface LQRResult {
  K_gain: number[][]
  eigenvalues: number[]
  controllable: boolean
  closed_loop_poles: number[]
}

export interface ManeuverPlan {
  delta_v: number[][]   // [dvx, dvy, dvz][]
  times: number[]
  total_delta_v: number
  fuel_mass: number
}

export interface EKFState {
  state_estimate: number[]
  covariance: number[][]
  innovation: number[]
}

export function useLQRController() {
  const queryClient = useQueryClient()

  const designMutation = useMutation({
    mutationFn: async (params: {
      system_matrices: {
        A: number[][]
        B: number[][]
      }
      config: LQRConfig
    }) => {
      const response = await api.control.computeFormationControl(params)
      return response.data as LQRResult
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastLQR'], data)
      toast.success('LQR controller designed')
    },
    onError: (error: any) => {
      toast.error(`LQR design failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    design: designMutation.mutate,
    designAsync: designMutation.mutateAsync,
    isLoading: designMutation.isPending,
    data: designMutation.data,
    error: designMutation.error,
    reset: designMutation.reset,
  }
}

export function useManeuverPlanning() {
  const queryClient = useQueryClient()

  const planMutation = useMutation({
    mutationFn: async (params: {
      initial_state: number[]
      target_state: number[]
      time_horizon: number
      constraints?: {
        max_delta_v: number
        min_time_between: number
      }
    }) => {
      const response = await api.control.planManeuvers(params)
      return response.data as ManeuverPlan
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['lastManeuverPlan'], data)
      toast.success('Maneuver plan computed')
    },
    onError: (error: any) => {
      toast.error(`Maneuver planning failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    plan: planMutation.mutate,
    planAsync: planMutation.mutateAsync,
    isLoading: planMutation.isPending,
    data: planMutation.data,
    error: planMutation.error,
  }
}

export function useStationKeeping() {
  const queryClient = useQueryClient()

  const computeMutation = useMutation({
    mutationFn: async (params: {
      current_state: number[]
      reference_orbit: {
        semi_major_axis: number
        eccentricity: number
        inclination: number
      }
      tolerance: {
        position_km: number
        velocity_km_s: number
      }
    }) => {
      const response = await api.control.computeStationKeeping(params)
      return response.data
    },
    onSuccess: () => {
      toast.success('Station-keeping maneuver computed')
    },
    onError: (error: any) => {
      toast.error(`Station-keeping computation failed: ${error.response?.data?.detail || error.message}`)
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

export function useFuelBudget() {
  const queryClient = useQueryClient()

  const computeMutation = useMutation({
    mutationFn: async (params: {
      maneuvers: ManeuverPlan
      spacecraft_mass: number
      specific_impulse: number
    }) => {
      const response = await api.control.computeFuelBudget(params)
      return response.data
    },
    onSuccess: () => {
      toast.success('Fuel budget computed')
    },
    onError: (error: any) => {
      toast.error(`Fuel budget computation failed: ${error.response?.data?.detail || error.message}`)
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

export function useLastLQR() {
  return useQuery<LQRResult | null>({
    queryKey: ['lastLQR'],
    queryFn: () => null,
    staleTime: Infinity,
  })
}

export function useLastManeuverPlan() {
  return useQuery<ManeuverPlan | null>({
    queryKey: ['lastManeuverPlan'],
    queryFn: () => null,
    staleTime: Infinity,
  })
}
