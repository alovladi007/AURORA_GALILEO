'use client'

/**
 * ML Panel Component
 *
 * Provides UI for PINN and U-Net model training and inference
 */

import React, { useState } from 'react'
import { Cpu, Play, RotateCcw, Plus, Trash2, Settings } from 'lucide-react'
import {
  useMLModels, useCreatePINN, useTrainPINN, usePINNInference,
  useCreateUNet, useTrainUNet, ModelInfo
} from '@/hooks/useML'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'

export function MLPanel() {
  const [modelType, setModelType] = useState<'pinn' | 'unet'>('pinn')
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)

  // PINN config
  const [pinnLayers, setPinnLayers] = useState([64, 64, 64])
  const [pinnActivation, setPinnActivation] = useState('tanh')

  // U-Net config
  const [unetChannels, setUnetChannels] = useState({ input: 1, output: 1 })

  // Training config
  const [epochs, setEpochs] = useState(100)
  const [batchSize, setBatchSize] = useState(32)
  const [learningRate, setLearningRate] = useState(0.001)

  // Demo training progress
  const [trainingProgress, setTrainingProgress] = useState<{epoch: number, loss: number, val_loss?: number}[]>([])

  const { data: models, isLoading: isLoadingModels } = useMLModels()
  const { create: createPINN, isLoading: isCreatingPINN } = useCreatePINN()
  const { train: trainPINN, isLoading: isTrainingPINN } = useTrainPINN()
  const { create: createUNet, isLoading: isCreatingUNet } = useCreateUNet()
  const { train: trainUNet, isLoading: isTrainingUNet } = useTrainUNet()

  const handleCreateModel = () => {
    if (modelType === 'pinn') {
      createPINN({
        hidden_layers: pinnLayers,
        activation: pinnActivation,
        physics_weight: 0.1,
      })
    } else {
      createUNet({
        input_channels: unetChannels.input,
        output_channels: unetChannels.output,
        features: [32, 64, 128, 256],
      })
    }
    setShowCreateModal(false)
  }

  const handleTrainModel = () => {
    if (!selectedModel) return

    // Simulate training progress for demo
    setTrainingProgress([])
    let epoch = 0
    const interval = setInterval(() => {
      epoch++
      const loss = Math.exp(-epoch * 0.05) + Math.random() * 0.01
      const val_loss = Math.exp(-epoch * 0.04) + Math.random() * 0.02
      setTrainingProgress(prev => [...prev, { epoch, loss, val_loss }])

      if (epoch >= epochs) {
        clearInterval(interval)
      }
    }, 100)

    if (modelType === 'pinn') {
      trainPINN({
        model_id: selectedModel,
        epochs,
        batch_size: batchSize,
        learning_rate: learningRate,
      })
    } else {
      trainUNet({
        model_id: selectedModel,
        epochs,
        batch_size: batchSize,
        learning_rate: learningRate,
      })
    }
  }

  const filteredModels = models?.filter(m => m.model_type === modelType) || []
  const isTraining = isTrainingPINN || isTrainingUNet
  const isCreating = isCreatingPINN || isCreatingUNet

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <Cpu className="w-7 h-7 text-pink-500" />
            Machine Learning
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Train and deploy PINN and U-Net models
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-lg transition-colors"
        >
          <Plus className="w-5 h-5" />
          New Model
        </button>
      </div>

      {/* Model Type Toggle */}
      <div className="flex gap-2 p-1 bg-gray-100 dark:bg-gray-700 rounded-lg w-fit">
        <button
          onClick={() => setModelType('pinn')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            modelType === 'pinn'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          PINN (Physics-Informed)
        </button>
        <button
          onClick={() => setModelType('unet')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            modelType === 'unet'
              ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow'
              : 'text-gray-600 dark:text-gray-300'
          }`}
        >
          U-Net (Denoising)
        </button>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Model List */}
        <div className="col-span-1 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {modelType === 'pinn' ? 'PINN' : 'U-Net'} Models
          </h3>

          {isLoadingModels ? (
            <div className="flex items-center justify-center py-8">
              <RotateCcw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : filteredModels.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <Cpu className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No models created yet</p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="mt-3 text-sm text-pink-600 dark:text-pink-400 hover:underline"
              >
                Create your first model
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredModels.map((model) => (
                <button
                  key={model.model_id}
                  onClick={() => setSelectedModel(model.model_id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedModel === model.model_id
                      ? 'bg-pink-50 dark:bg-pink-900/20 border-pink-300 dark:border-pink-700'
                      : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-medium text-gray-900 dark:text-white">
                      {model.model_id.slice(0, 8)}...
                    </div>
                    <span className={`text-xs px-2 py-1 rounded ${
                      model.training_status === 'trained'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                        : model.training_status === 'training'
                        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                    }`}>
                      {model.training_status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Created: {new Date(model.created_at).toLocaleDateString()}
                  </div>
                  {model.metrics?.final_loss && (
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Loss: {model.metrics.final_loss.toExponential(2)}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Training Panel */}
        <div className="col-span-2 space-y-6">
          {/* Training Configuration */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Training Configuration
            </h3>

            <div className="grid grid-cols-3 gap-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Epochs
                </label>
                <input
                  type="number"
                  value={epochs}
                  onChange={(e) => setEpochs(parseInt(e.target.value) || 1)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Batch Size
                </label>
                <input
                  type="number"
                  value={batchSize}
                  onChange={(e) => setBatchSize(parseInt(e.target.value) || 1)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Learning Rate
                </label>
                <input
                  type="number"
                  step="0.0001"
                  value={learningRate}
                  onChange={(e) => setLearningRate(parseFloat(e.target.value) || 0.001)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>

            <button
              onClick={handleTrainModel}
              disabled={!selectedModel || isTraining}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-pink-600 hover:bg-pink-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isTraining ? (
                <>
                  <RotateCcw className="w-5 h-5 animate-spin" />
                  Training...
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  Start Training
                </>
              )}
            </button>
          </div>

          {/* Training Progress */}
          {trainingProgress.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Training Progress
                </h3>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  Epoch {trainingProgress.length} / {epochs}
                </div>
              </div>

              {/* Progress Bar */}
              <div className="mb-4">
                <div className="bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-pink-600 h-2 rounded-full transition-all"
                    style={{ width: `${(trainingProgress.length / epochs) * 100}%` }}
                  />
                </div>
              </div>

              {/* Loss Chart */}
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trainingProgress}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="epoch" stroke="#9CA3AF" />
                    <YAxis stroke="#9CA3AF" scale="log" domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#F9FAFB'
                      }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="loss"
                      name="Training Loss"
                      stroke="#EC4899"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="val_loss"
                      name="Validation Loss"
                      stroke="#8B5CF6"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Current Metrics */}
              {trainingProgress.length > 0 && (
                <div className="grid grid-cols-2 gap-4 mt-4">
                  <div className="bg-pink-50 dark:bg-pink-900/20 rounded-lg p-3">
                    <div className="text-xs text-pink-600 dark:text-pink-400">Training Loss</div>
                    <div className="text-xl font-bold text-pink-900 dark:text-pink-100">
                      {trainingProgress[trainingProgress.length - 1].loss.toExponential(3)}
                    </div>
                  </div>
                  <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3">
                    <div className="text-xs text-purple-600 dark:text-purple-400">Validation Loss</div>
                    <div className="text-xl font-bold text-purple-900 dark:text-purple-100">
                      {trainingProgress[trainingProgress.length - 1].val_loss?.toExponential(3) || 'N/A'}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Create Model Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Create New {modelType === 'pinn' ? 'PINN' : 'U-Net'} Model
            </h3>

            {modelType === 'pinn' ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Hidden Layers (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={pinnLayers.join(', ')}
                    onChange={(e) => setPinnLayers(e.target.value.split(',').map(s => parseInt(s.trim()) || 64))}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="64, 64, 64"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Activation Function
                  </label>
                  <select
                    value={pinnActivation}
                    onChange={(e) => setPinnActivation(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  >
                    <option value="tanh">Tanh</option>
                    <option value="relu">ReLU</option>
                    <option value="silu">SiLU</option>
                    <option value="gelu">GELU</option>
                  </select>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Input Channels
                  </label>
                  <input
                    type="number"
                    value={unetChannels.input}
                    onChange={(e) => setUnetChannels({ ...unetChannels, input: parseInt(e.target.value) || 1 })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Output Channels
                  </label>
                  <input
                    type="number"
                    value={unetChannels.output}
                    onChange={(e) => setUnetChannels({ ...unetChannels, output: parseInt(e.target.value) || 1 })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
              </div>
            )}

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                className="flex-1 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateModel}
                disabled={isCreating}
                className="flex-1 px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {isCreating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MLPanel
