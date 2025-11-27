/**
 * ML Service Hook
 *
 * Provides React Query hooks for PINN and U-Net model operations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client-full'
import toast from 'react-hot-toast'

export interface ModelConfig {
  model_type: 'pinn' | 'unet'
  hidden_layers?: number[]
  activation?: string
  learning_rate?: number
}

export interface TrainingConfig {
  epochs: number
  batch_size: number
  learning_rate: number
  validation_split?: number
}

export interface TrainingProgress {
  epoch: number
  total_epochs: number
  loss: number
  val_loss?: number
  metrics?: Record<string, number>
}

export interface ModelInfo {
  model_id: string
  model_type: string
  created_at: string
  training_status: 'untrained' | 'training' | 'trained' | 'failed'
  config: ModelConfig
  metrics?: {
    final_loss: number
    val_loss?: number
    epochs_trained: number
  }
}

export function useMLModels() {
  return useQuery<ModelInfo[]>({
    queryKey: ['ml-models'],
    queryFn: async () => {
      const response = await api.ml.listModels()
      return response.data.models || []
    },
    refetchInterval: 10000,
  })
}

export function useCreatePINN() {
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: async (params: {
      hidden_layers: number[]
      activation: string
      physics_weight?: number
    }) => {
      const response = await api.ml.createPinnModel(params)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] })
      toast.success('PINN model created')
    },
    onError: (error: any) => {
      toast.error(`Failed to create PINN: ${error.response?.data?.detail || error.message}`)
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

export function useTrainPINN() {
  const queryClient = useQueryClient()

  const trainMutation = useMutation({
    mutationFn: async (params: {
      model_id: string
      training_data?: {
        inputs: number[][]
        targets: number[][]
      }
      epochs: number
      batch_size: number
      learning_rate: number
    }) => {
      const response = await api.ml.trainPinn(params)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] })
      toast.success('PINN training complete')
    },
    onError: (error: any) => {
      toast.error(`PINN training failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    train: trainMutation.mutate,
    trainAsync: trainMutation.mutateAsync,
    isLoading: trainMutation.isPending,
    data: trainMutation.data,
    error: trainMutation.error,
  }
}

export function usePINNInference() {
  const inferMutation = useMutation({
    mutationFn: async (params: {
      model_id: string
      inputs: number[][]
    }) => {
      const response = await api.ml.pinnInference(params)
      return response.data
    },
    onError: (error: any) => {
      toast.error(`PINN inference failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    infer: inferMutation.mutate,
    inferAsync: inferMutation.mutateAsync,
    isLoading: inferMutation.isPending,
    data: inferMutation.data,
    error: inferMutation.error,
  }
}

export function useCreateUNet() {
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: async (params: {
      input_channels: number
      output_channels: number
      features?: number[]
    }) => {
      const response = await api.ml.createUnetModel(params)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] })
      toast.success('U-Net model created')
    },
    onError: (error: any) => {
      toast.error(`Failed to create U-Net: ${error.response?.data?.detail || error.message}`)
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

export function useTrainUNet() {
  const queryClient = useQueryClient()

  const trainMutation = useMutation({
    mutationFn: async (params: {
      model_id: string
      training_images?: number[][][]
      target_images?: number[][][]
      epochs: number
      batch_size: number
      learning_rate: number
    }) => {
      const response = await api.ml.trainUnet(params)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] })
      toast.success('U-Net training complete')
    },
    onError: (error: any) => {
      toast.error(`U-Net training failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    train: trainMutation.mutate,
    trainAsync: trainMutation.mutateAsync,
    isLoading: trainMutation.isPending,
    data: trainMutation.data,
    error: trainMutation.error,
  }
}

export function useUNetInference() {
  const inferMutation = useMutation({
    mutationFn: async (params: {
      model_id: string
      input_image: number[][]
    }) => {
      const response = await api.ml.unetInference(params)
      return response.data
    },
    onError: (error: any) => {
      toast.error(`U-Net inference failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    infer: inferMutation.mutate,
    inferAsync: inferMutation.mutateAsync,
    isLoading: inferMutation.isPending,
    data: inferMutation.data,
    error: inferMutation.error,
  }
}

export function useUNetUncertainty() {
  const uncertaintyMutation = useMutation({
    mutationFn: async (params: {
      model_id: string
      input_image: number[][]
      n_samples?: number
    }) => {
      const response = await api.ml.unetUncertainty(params)
      return response.data
    },
    onError: (error: any) => {
      toast.error(`Uncertainty estimation failed: ${error.response?.data?.detail || error.message}`)
    },
  })

  return {
    estimate: uncertaintyMutation.mutate,
    estimateAsync: uncertaintyMutation.mutateAsync,
    isLoading: uncertaintyMutation.isPending,
    data: uncertaintyMutation.data,
    error: uncertaintyMutation.error,
  }
}
