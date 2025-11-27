/**
 * Emulator Service Hook
 *
 * Provides React Query hooks for optical bench emulator operations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client-full'
import toast from 'react-hot-toast'

export interface EmulatorConfig {
  sample_rate: number       // Hz
  wavelength: number        // meters
  noise_floor: number       // rad/sqrt(Hz)
  initial_range: number     // km
  initial_range_rate: number  // km/s
}

export interface EmulatorState {
  emulator_id: string
  status: 'stopped' | 'running' | 'paused'
  current_time: number
  phase: number
  range: number
  range_rate: number
  noise_level: number
}

export interface SignalHistory {
  times: number[]
  phase: number[]
  range: number[]
  range_rate: number[]
  noise: number[]
}

export interface EmulatorEvent {
  event_type: 'vibration' | 'thermal' | 'glitch' | 'dropout'
  magnitude: number
  duration: number
  start_time?: number
}

export function useEmulatorStatus(emulatorId: string = 'default') {
  return useQuery<EmulatorState>({
    queryKey: ['emulator-status', emulatorId],
    queryFn: async () => {
      const response = await api.emulator.getCurrentState(emulatorId)
      return response.data
    },
    refetchInterval: 1000,  // Poll every second when active
    enabled: true,
  })
}

export function useEmulatorHistory(emulatorId: string = 'default', limit: number = 1000) {
  return useQuery<SignalHistory>({
    queryKey: ['emulator-history', emulatorId, limit],
    queryFn: async () => {
      const response = await api.emulator.getSignalHistory(emulatorId, { limit })
      return response.data
    },
    refetchInterval: 2000,
    enabled: true,
  })
}

export function useCreateEmulator() {
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: async (config: EmulatorConfig) => {
      const response = await api.emulator.createEmulator(config)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emulator-status'] })
      toast.success('Emulator created')
    },
    onError: (error: any) => {
      toast.error(`Failed to create emulator: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    create: createMutation.mutate,
    createAsync: createMutation.mutateAsync,
    isLoading: createMutation.isPending,
    data: createMutation.data,
    error: createMutation.error,
  }
}

export function useEmulatorControl(emulatorId: string = 'default') {
  const queryClient = useQueryClient()

  const startMutation = useMutation({
    mutationFn: async () => {
      const response = await api.emulator.startEmulator(emulatorId)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emulator-status', emulatorId] })
      toast.success('Emulator started')
    },
    onError: (error: any) => {
      toast.error(`Failed to start emulator: ${error.response?.data?.detail || error.message}`)
    },
  })

  const stopMutation = useMutation({
    mutationFn: async () => {
      const response = await api.emulator.stopEmulator(emulatorId)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emulator-status', emulatorId] })
      toast.success('Emulator stopped')
    },
    onError: (error: any) => {
      toast.error(`Failed to stop emulator: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    start: startMutation.mutate,
    stop: stopMutation.mutate,
    isStarting: startMutation.isPending,
    isStopping: stopMutation.isPending,
  }
}

export function useInjectEvent(emulatorId: string = 'default') {
  const queryClient = useQueryClient()

  const injectMutation = useMutation({
    mutationFn: async (event: EmulatorEvent) => {
      const response = await api.emulator.injectEvent(emulatorId, event)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emulator-history', emulatorId] })
      toast.success('Event injected')
    },
    onError: (error: any) => {
      toast.error(`Failed to inject event: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    inject: injectMutation.mutate,
    injectAsync: injectMutation.mutateAsync,
    isLoading: injectMutation.isPending,
    data: injectMutation.data,
    error: injectMutation.error,
  }
}
