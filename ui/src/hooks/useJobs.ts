import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'

interface Job {
  id: string
  job_type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  started_at?: string
  completed_at?: string
  updated_at: string
  error_message?: string
  config?: any
  result?: any
}

export function useJobs() {
  const queryClient = useQueryClient()

  const { data: jobs, isLoading, refetch } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: async () => {
      const response = await apiClient.get('/ops/jobs')
      return response.data
    },
    enabled: true, // Enable without auth for now
    refetchInterval: 5000, // Refresh every 5 seconds
  })

  const createJobMutation = useMutation({
    mutationFn: async (jobData: { type: string; config: any }) => {
      const endpoint = `/ops/${jobData.type}`
      const response = await apiClient.post(endpoint, jobData.config)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const cancelJobMutation = useMutation({
    mutationFn: async (jobId: string) => {
      const response = await apiClient.delete(`/ops/jobs/${jobId}`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  return {
    jobs,
    isLoading,
    refetch,
    createJob: createJobMutation.mutate,
    cancelJob: cancelJobMutation.mutate,
    isCreating: createJobMutation.isPending,
    isCancelling: cancelJobMutation.isPending,
  }
}
