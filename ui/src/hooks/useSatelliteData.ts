import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import { subHours } from 'date-fns'
import toast from 'react-hot-toast'

interface UseSatelliteDataProps {
  satellites: string[]
  time: Date
}

export function useSatelliteData({ satellites, time }: UseSatelliteDataProps) {
  return useQuery({
    queryKey: ['satelliteData', satellites, time.toISOString()],
    queryFn: async () => {
      if (satellites.length === 0) return []

      // Query telemetry for time window around the specified time
      const start_time = subHours(time, 1).toISOString()
      const end_time = new Date(time.getTime() + 3600000).toISOString()

      try {
        const response = await api.queryTelemetry({
          satellite_ids: satellites,
          start_time,
          end_time,
          page_size: 100,
        })

        // Transform API response to component format
        return response.data.telemetry?.map((t: any) => ({
          id: t.satellite_id,
          position: {
            lat: t.location.latitude,
            lon: t.location.longitude,
            alt: t.location.altitude
          },
          velocity: {
            x: t.velocity_x || 0,
            y: t.velocity_y || 0,
            z: t.velocity_z || 0
          },
          temperature: t.temperature,
          battery_level: t.battery_level,
          timestamp: t.timestamp
        })) || []
      } catch (error) {
        console.warn('Failed to fetch satellite data, using mock data:', error)
        // Fallback to mock data for development
        return satellites.map(id => ({
          id,
          position: {
            lat: (Math.random() - 0.5) * 140,
            lon: (Math.random() - 0.5) * 360,
            alt: 450 + Math.random() * 20
          },
          velocity: {
            x: Math.random() * 7.5,
            y: Math.random() * 7.5,
            z: Math.random() * 0.1
          },
          temperature: 20 + Math.random() * 10,
          battery_level: 80 + Math.random() * 20
        }))
      }
    },
    enabled: satellites.length > 0,
    staleTime: 10000,
    refetchInterval: 30000,
  })
}

export function useQueryTelemetry(params: {
  satellite_ids: string[]
  start_time: string
  end_time: string
  page?: number
  page_size?: number
}) {
  return useQuery({
    queryKey: ['telemetry', params],
    queryFn: async () => {
      const response = await api.queryTelemetry(params)
      return response.data
    },
    enabled: params.satellite_ids.length > 0,
  })
}

export function useIngestTelemetry() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: {
      satellite_id: string
      location: { latitude: number; longitude: number; altitude: number }
      temperature?: number
      battery_level?: number
    }) => {
      const response = await api.ingestTelemetry(data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['telemetry'] })
      toast.success('Telemetry ingested')
    },
    onError: (error: any) => {
      toast.error(`Failed to ingest: ${error.response?.data?.detail || error.message}`)
    },
  })
}

export function useQueryGravity(params: {
  satellite_ids?: string[]
  start_time?: string
  end_time?: string
  min_latitude?: number
  max_latitude?: number
  min_longitude?: number
  max_longitude?: number
}) {
  return useQuery({
    queryKey: ['gravity', params],
    queryFn: async () => {
      const response = await api.queryGravity(params)
      return response.data
    },
  })
}

export function useExportData() {
  return useMutation({
    mutationFn: async (params: {
      export_type: 'telemetry' | 'gravity'
      satellite_ids?: string[]
      start_time?: string
      end_time?: string
      format: 'csv' | 'netcdf' | 'parquet'
    }) => {
      const response = await api.exportData(params)
      return response.data
    },
    onSuccess: (data) => {
      toast.success(`Export ready: ${data.download_url}`)
      // Open download link
      window.open(data.download_url, '_blank')
    },
    onError: (error: any) => {
      toast.error(`Export failed: ${error.response?.data?.detail || error.message}`)
    },
  })
}
