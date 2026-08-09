/**
 * Satellite Control Service Hook
 *
 * Provides React Query hooks for satellite control operations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import toast from 'react-hot-toast'

export function useSatellites(status?: string) {
  return useQuery({
    queryKey: ['satellites', status],
    queryFn: async () => {
      const response = await api.listSatellites(status)
      return response.data
    },
    refetchInterval: 10000, // Poll every 10 seconds
  })
}

export function useSatelliteStatus(satelliteId: string | null) {
  return useQuery({
    queryKey: ['satellite', satelliteId],
    queryFn: async () => {
      if (!satelliteId) return null
      const response = await api.getSatelliteStatus(satelliteId)
      return response.data
    },
    enabled: !!satelliteId,
    refetchInterval: 5000, // Poll every 5 seconds for real-time status
  })
}

export function useSendCommand() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: {
      satelliteId: string
      command_type: string
      parameters?: Record<string, string>
      priority?: number
      wait_for_ack?: boolean
    }) => {
      const { satelliteId, ...data } = params
      const response = await api.sendCommand(satelliteId, data)
      return response.data
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['satellite', variables.satelliteId] })
      toast.success(`Command sent: ${data.command_id}`)
    },
    onError: (error: any) => {
      toast.error(`Command failed: ${error.response?.data?.detail || error.message}`)
    },
  })
}

export function useCommandStatus(commandId: string | null) {
  return useQuery({
    queryKey: ['command', commandId],
    queryFn: async () => {
      if (!commandId) return null
      const response = await api.getCommandStatus(commandId)
      return response.data
    },
    enabled: !!commandId,
    refetchInterval: (query) => {
      // Poll more frequently if command is pending
      const status = query.state.data?.status
      if (status === 'pending' || status === 'sent') return 2000
      return false // Stop polling if completed/failed
    },
  })
}

export function useOrbitPrediction(
  satelliteId: string | null,
  params: {
    start_time: string
    end_time: string
    time_step_seconds?: number
  }
) {
  return useQuery({
    queryKey: ['orbit-prediction', satelliteId, params],
    queryFn: async () => {
      if (!satelliteId) return null
      const response = await api.getOrbitPrediction(satelliteId, params)
      return response.data
    },
    enabled: !!satelliteId,
    staleTime: 300000, // 5 minutes
  })
}
