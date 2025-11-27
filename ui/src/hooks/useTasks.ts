/**
 * Task Service Hook
 *
 * Provides React Query hooks for Celery task management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client-full'
import toast from 'react-hot-toast'

export interface Task {
  task_id: string
  task_name: string
  status: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'REVOKED' | 'RETRY'
  ready: boolean
  successful?: boolean
  failed?: boolean
  worker?: string
  result?: any
  error?: string
  progress?: number
  current?: number
  total?: number
  submitted_at?: string
  started_at?: string
  completed_at?: string
}

export interface WorkerInfo {
  name: string
  pool: string
  max_concurrency: number
  active_tasks: number
  registered_tasks: number
  uptime: number
  status: 'online' | 'offline'
}

export interface TaskSubmission {
  task_name: string
  parameters: Record<string, any>
  priority?: number
  queue?: string
}

export function useActiveTasks() {
  return useQuery<Task[]>({
    queryKey: ['active-tasks'],
    queryFn: async () => {
      const response = await api.task.listActiveTasks()
      return response.data.active_tasks || []
    },
    refetchInterval: 3000,  // Poll every 3 seconds
  })
}

export function useScheduledTasks() {
  return useQuery<Task[]>({
    queryKey: ['scheduled-tasks'],
    queryFn: async () => {
      const response = await api.task.listScheduledTasks()
      return response.data.scheduled_tasks || []
    },
    refetchInterval: 5000,
  })
}

export function useWorkerStats() {
  return useQuery<WorkerInfo[]>({
    queryKey: ['worker-stats'],
    queryFn: async () => {
      const response = await api.task.getWorkerStats()
      return response.data.workers || []
    },
    refetchInterval: 10000,
  })
}

export function useTaskStatus(taskId: string | null) {
  return useQuery<Task>({
    queryKey: ['task-status', taskId],
    queryFn: async () => {
      if (!taskId) throw new Error('No task ID')
      const response = await api.task.getTaskStatus(taskId)
      return response.data
    },
    enabled: !!taskId,
    refetchInterval: (data) => {
      // Stop polling when task is complete
      if (data?.ready) return false
      return 2000
    },
  })
}

export function useTaskResult(taskId: string | null) {
  return useQuery({
    queryKey: ['task-result', taskId],
    queryFn: async () => {
      if (!taskId) throw new Error('No task ID')
      const response = await api.task.getTaskResult(taskId)
      return response.data
    },
    enabled: !!taskId,
  })
}

export function useSubmitTask() {
  const queryClient = useQueryClient()

  const submitMutation = useMutation({
    mutationFn: async (submission: TaskSubmission) => {
      const response = await api.task.submitTask(submission)
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['active-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['scheduled-tasks'] })
      toast.success(`Task submitted: ${data.task_id?.slice(0, 8)}...`)
    },
    onError: (error: any) => {
      toast.error(`Failed to submit task: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    submit: submitMutation.mutate,
    submitAsync: submitMutation.mutateAsync,
    isLoading: submitMutation.isPending,
    data: submitMutation.data,
    error: submitMutation.error,
  }
}

export function useSubmitTaskChain() {
  const queryClient = useQueryClient()

  const submitMutation = useMutation({
    mutationFn: async (tasks: TaskSubmission[]) => {
      const response = await api.task.submitChain({ tasks })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['active-tasks'] })
      toast.success('Task chain submitted')
    },
    onError: (error: any) => {
      toast.error(`Failed to submit chain: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    submit: submitMutation.mutate,
    submitAsync: submitMutation.mutateAsync,
    isLoading: submitMutation.isPending,
    data: submitMutation.data,
    error: submitMutation.error,
  }
}

export function useSubmitTaskGroup() {
  const queryClient = useQueryClient()

  const submitMutation = useMutation({
    mutationFn: async (tasks: TaskSubmission[]) => {
      const response = await api.task.submitGroup({ tasks })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['active-tasks'] })
      toast.success('Task group submitted')
    },
    onError: (error: any) => {
      toast.error(`Failed to submit group: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    submit: submitMutation.mutate,
    submitAsync: submitMutation.mutateAsync,
    isLoading: submitMutation.isPending,
    data: submitMutation.data,
    error: submitMutation.error,
  }
}

export function useCancelTask() {
  const queryClient = useQueryClient()

  const cancelMutation = useMutation({
    mutationFn: async (taskId: string) => {
      const response = await api.task.cancelTask(taskId)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['active-tasks'] })
      toast.success('Task cancelled')
    },
    onError: (error: any) => {
      toast.error(`Failed to cancel task: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    cancel: cancelMutation.mutate,
    cancelAsync: cancelMutation.mutateAsync,
    isLoading: cancelMutation.isPending,
  }
}

export function useRetryTask() {
  const queryClient = useQueryClient()

  const retryMutation = useMutation({
    mutationFn: async (taskId: string) => {
      const response = await api.task.retryTask(taskId)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['active-tasks'] })
      toast.success('Task retry submitted')
    },
    onError: (error: any) => {
      toast.error(`Failed to retry task: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    retry: retryMutation.mutate,
    retryAsync: retryMutation.mutateAsync,
    isLoading: retryMutation.isPending,
  }
}
