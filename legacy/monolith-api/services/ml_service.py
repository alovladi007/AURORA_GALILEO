"""
ML Service for GeoSense Platform API

Provides business logic for machine learning operations:
- Physics-Informed Neural Network (PINN) training and inference
- U-Net model training for gravity field denoising
- Model management (save/load)
- Synthetic data generation
- Uncertainty quantification with MC Dropout

This service bridges API endpoints with ML modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
import torch
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

# Import ML modules
try:
    from ml.pinn import GravityPINN, PINNTrainer
    from ml.unet import UNetGravity, UNetTrainer, MCDropoutUncertainty
    from ml.train import (
        generate_synthetic_phase_gravity_pairs,
        PhaseGravityDataset
    )
    from torch.utils.data import DataLoader, random_split
    ML_IMPORTS_AVAILABLE = True
except ImportError as e:
    ML_IMPORTS_AVAILABLE = False
    print(f"ML imports not available: {e}")


@dataclass
class TrainingResult:
    """Container for training results."""
    model_id: str
    final_train_loss: float
    final_val_loss: float
    epochs_trained: int
    history: Dict[str, List[float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'model_id': self.model_id,
            'final_train_loss': self.final_train_loss,
            'final_val_loss': self.final_val_loss,
            'epochs_trained': self.epochs_trained,
            'history': self.history
        }


@dataclass
class InferenceResult:
    """Container for inference results."""
    predictions: np.ndarray
    input_shape: Tuple[int, ...]
    output_shape: Tuple[int, ...]
    uncertainty: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'predictions': self.predictions.tolist(),
            'input_shape': list(self.input_shape),
            'output_shape': list(self.output_shape)
        }
        if self.uncertainty is not None:
            result['uncertainty'] = self.uncertainty.tolist()
        return result


class MLService:
    """
    Service for machine learning operations.

    Provides high-level functions for PINN and U-Net training,
    inference, and model management.
    """

    def __init__(self, models_dir: str = './models'):
        """Initialize ML service."""
        if not ML_IMPORTS_AVAILABLE:
            print("Warning: ML modules not available.")

        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Cache for loaded models
        self._pinn_models = {}
        self._unet_models = {}
        self._trainers = {}

        # Device selection
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"ML Service using device: {self.device}")

    # =================================================================
    # PINN Operations
    # =================================================================

    def create_pinn_model(
        self,
        model_id: str = 'default',
        hidden_layers: List[int] = [64, 128, 128, 64],
        activation: str = 'tanh'
    ) -> Dict[str, Any]:
        """
        Create PINN model for gravity field prediction.

        Args:
            model_id: Unique identifier for model
            hidden_layers: List of hidden layer sizes
            activation: Activation function ('tanh', 'relu', 'silu')

        Returns:
            Dictionary with model configuration
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        model = GravityPINN(
            hidden_layers=hidden_layers,
            activation=activation
        )

        # Cache model
        self._pinn_models[model_id] = model

        # Count parameters
        n_params = sum(p.numel() for p in model.parameters())

        return {
            'model_id': model_id,
            'model_type': 'PINN',
            'hidden_layers': hidden_layers,
            'activation': activation,
            'n_parameters': n_params,
            'device': self.device,
            'status': 'created'
        }

    def train_pinn(
        self,
        model_id: str = 'default',
        n_samples: int = 5000,
        epochs: int = 100,
        batch_size: int = 64,
        lr: float = 1e-3,
        lambda_physics: float = 1.0,
        val_split: float = 0.2
    ) -> TrainingResult:
        """
        Train PINN model with synthetic data.

        Args:
            model_id: Model identifier
            n_samples: Number of training samples to generate
            epochs: Training epochs
            batch_size: Batch size
            lr: Learning rate
            lambda_physics: Weight for physics loss
            val_split: Validation split fraction

        Returns:
            TrainingResult with history and metrics
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        if model_id not in self._pinn_models:
            raise ValueError(f"Model {model_id} not found. Create model first.")

        model = self._pinn_models[model_id]

        # Generate synthetic data
        print(f"Generating {n_samples} synthetic samples...")
        coords, densities, gravity = self._generate_pinn_data(n_samples)

        # Create dataset
        from ml.pinn import GravityDataset
        dataset = GravityDataset(coords, densities, gravity)

        # Train/val split
        val_size = int(len(dataset) * val_split)
        train_size = len(dataset) - val_size
        train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        # Create trainer
        trainer = PINNTrainer(model, device=self.device)
        self._trainers[f'pinn_{model_id}'] = trainer

        # Train
        print(f"Training PINN model '{model_id}'...")
        history = trainer.train(
            train_loader=train_loader,
            val_loader=val_loader,
            epochs=epochs,
            lr=lr,
            lambda_physics=lambda_physics
        )

        return TrainingResult(
            model_id=model_id,
            final_train_loss=history['train_loss'][-1],
            final_val_loss=history['val_loss'][-1] if history['val_loss'] else 0.0,
            epochs_trained=epochs,
            history=history
        )

    def pinn_inference(
        self,
        model_id: str,
        coordinates: np.ndarray,
        densities: np.ndarray
    ) -> InferenceResult:
        """
        Run inference with trained PINN model.

        Args:
            model_id: Model identifier
            coordinates: Coordinates array (N, 3) [x, y, z]
            densities: Density values (N,)

        Returns:
            InferenceResult with predicted gravity field
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        if model_id not in self._pinn_models:
            raise ValueError(f"Model {model_id} not found")

        model = self._pinn_models[model_id]
        model.eval()

        # Prepare input
        coords_tensor = torch.FloatTensor(coordinates)
        densities_tensor = torch.FloatTensor(densities).unsqueeze(1)
        x = torch.cat([coords_tensor, densities_tensor], dim=1)
        x = x.to(self.device)

        # Inference
        with torch.no_grad():
            gravity_pred = model(x)

        gravity_np = gravity_pred.cpu().numpy()

        return InferenceResult(
            predictions=gravity_np,
            input_shape=coordinates.shape,
            output_shape=gravity_np.shape
        )

    # =================================================================
    # U-Net Operations
    # =================================================================

    def create_unet_model(
        self,
        model_id: str = 'default',
        in_channels: int = 1,
        out_channels: int = 1,
        base_channels: int = 64,
        depth: int = 4,
        dropout: float = 0.1
    ) -> Dict[str, Any]:
        """
        Create U-Net model for gravity field denoising.

        Args:
            model_id: Unique identifier
            in_channels: Input channels (e.g., 1 for phase)
            out_channels: Output channels (e.g., 1 for gravity)
            base_channels: Base number of channels
            depth: Network depth
            dropout: Dropout probability

        Returns:
            Dictionary with model configuration
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        model = UNetGravity(
            in_channels=in_channels,
            out_channels=out_channels,
            base_channels=base_channels,
            depth=depth,
            dropout=dropout
        )

        # Cache model
        self._unet_models[model_id] = model

        # Count parameters
        n_params = sum(p.numel() for p in model.parameters())

        return {
            'model_id': model_id,
            'model_type': 'UNet',
            'in_channels': in_channels,
            'out_channels': out_channels,
            'base_channels': base_channels,
            'depth': depth,
            'dropout': dropout,
            'n_parameters': n_params,
            'device': self.device,
            'status': 'created'
        }

    def train_unet(
        self,
        model_id: str = 'default',
        n_samples: int = 500,
        image_size: int = 128,
        noise_level: float = 0.1,
        epochs: int = 100,
        batch_size: int = 8,
        lr: float = 1e-3,
        loss_fn: str = 'mse',
        val_split: float = 0.2
    ) -> TrainingResult:
        """
        Train U-Net model with synthetic phase-gravity pairs.

        Args:
            model_id: Model identifier
            n_samples: Number of training samples
            image_size: Size of images
            noise_level: Noise level for phase data
            epochs: Training epochs
            batch_size: Batch size
            lr: Learning rate
            loss_fn: Loss function ('mse', 'mae', 'huber')
            val_split: Validation split

        Returns:
            TrainingResult with history
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        if model_id not in self._unet_models:
            raise ValueError(f"Model {model_id} not found")

        model = self._unet_models[model_id]

        # Generate synthetic data
        print(f"Generating {n_samples} phase-gravity pairs...")
        phase_data, gravity_data = generate_synthetic_phase_gravity_pairs(
            n_samples=n_samples,
            image_size=image_size,
            noise_level=noise_level
        )

        # Create dataset
        dataset = PhaseGravityDataset(phase_data, gravity_data)

        # Train/val split
        val_size = int(len(dataset) * val_split)
        train_size = len(dataset) - val_size
        train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        # Create trainer
        trainer = UNetTrainer(model, device=self.device)
        self._trainers[f'unet_{model_id}'] = trainer

        # Train
        print(f"Training U-Net model '{model_id}'...")
        history = trainer.train(
            train_loader=train_loader,
            val_loader=val_loader,
            epochs=epochs,
            lr=lr,
            loss_fn=loss_fn
        )

        return TrainingResult(
            model_id=model_id,
            final_train_loss=history['train_loss'][-1],
            final_val_loss=history['val_loss'][-1] if history['val_loss'] else 0.0,
            epochs_trained=epochs,
            history=history
        )

    def unet_inference(
        self,
        model_id: str,
        phase_data: np.ndarray
    ) -> InferenceResult:
        """
        Run inference with trained U-Net model.

        Args:
            model_id: Model identifier
            phase_data: Phase measurements (H, W) or (N, H, W)

        Returns:
            InferenceResult with denoised gravity field
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        if model_id not in self._unet_models:
            raise ValueError(f"Model {model_id} not found")

        model = self._unet_models[model_id]
        model.eval()

        # Prepare input
        if phase_data.ndim == 2:
            # Single image: (H, W) -> (1, 1, H, W)
            phase_tensor = torch.FloatTensor(phase_data).unsqueeze(0).unsqueeze(0)
        elif phase_data.ndim == 3:
            # Batch: (N, H, W) -> (N, 1, H, W)
            phase_tensor = torch.FloatTensor(phase_data).unsqueeze(1)
        else:
            raise ValueError(f"Invalid phase_data shape: {phase_data.shape}")

        phase_tensor = phase_tensor.to(self.device)

        # Inference
        with torch.no_grad():
            gravity_pred = model(phase_tensor)

        gravity_np = gravity_pred.cpu().numpy().squeeze()

        return InferenceResult(
            predictions=gravity_np,
            input_shape=phase_data.shape,
            output_shape=gravity_np.shape
        )

    def unet_uncertainty_estimation(
        self,
        model_id: str,
        phase_data: np.ndarray,
        n_samples: int = 50
    ) -> InferenceResult:
        """
        Estimate uncertainty using MC Dropout.

        Args:
            model_id: Model identifier
            phase_data: Phase measurements
            n_samples: Number of MC dropout samples

        Returns:
            InferenceResult with predictions and uncertainty
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        if model_id not in self._unet_models:
            raise ValueError(f"Model {model_id} not found")

        model = self._unet_models[model_id]

        # Prepare input
        if phase_data.ndim == 2:
            phase_tensor = torch.FloatTensor(phase_data).unsqueeze(0).unsqueeze(0)
        else:
            phase_tensor = torch.FloatTensor(phase_data).unsqueeze(1)

        phase_tensor = phase_tensor.to(self.device)

        # MC Dropout uncertainty
        mc_dropout = MCDropoutUncertainty(model, n_samples=n_samples)
        mean_pred, std_pred = mc_dropout.predict_with_uncertainty(phase_tensor)

        mean_np = mean_pred.cpu().numpy().squeeze()
        std_np = std_pred.cpu().numpy().squeeze()

        return InferenceResult(
            predictions=mean_np,
            input_shape=phase_data.shape,
            output_shape=mean_np.shape,
            uncertainty=std_np
        )

    # =================================================================
    # Model Management
    # =================================================================

    def save_pinn_model(self, model_id: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Save PINN model to disk.

        Args:
            model_id: Model identifier
            filename: Optional filename (default: {model_id}_pinn.pth)

        Returns:
            Dictionary with save info
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        if model_id not in self._pinn_models:
            raise ValueError(f"Model {model_id} not found")

        if filename is None:
            filename = f"{model_id}_pinn.pth"

        filepath = self.models_dir / filename

        trainer_key = f'pinn_{model_id}'
        if trainer_key in self._trainers:
            trainer = self._trainers[trainer_key]
            trainer.save_checkpoint(str(filepath))
        else:
            # Save model state dict only
            torch.save(self._pinn_models[model_id].state_dict(), filepath)

        return {
            'model_id': model_id,
            'filepath': str(filepath),
            'status': 'saved'
        }

    def load_pinn_model(
        self,
        model_id: str,
        filepath: str,
        hidden_layers: List[int] = [64, 128, 128, 64],
        activation: str = 'tanh'
    ) -> Dict[str, Any]:
        """
        Load PINN model from disk.

        Args:
            model_id: Model identifier
            filepath: Path to model file
            hidden_layers: Model architecture
            activation: Activation function

        Returns:
            Dictionary with load info
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        # Create model
        model = GravityPINN(hidden_layers=hidden_layers, activation=activation)

        # Load weights
        model.load_state_dict(torch.load(filepath, map_location=self.device))
        model.to(self.device)

        # Cache model
        self._pinn_models[model_id] = model

        return {
            'model_id': model_id,
            'filepath': filepath,
            'status': 'loaded'
        }

    def save_unet_model(self, model_id: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Save U-Net model to disk.

        Args:
            model_id: Model identifier
            filename: Optional filename

        Returns:
            Dictionary with save info
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        if model_id not in self._unet_models:
            raise ValueError(f"Model {model_id} not found")

        if filename is None:
            filename = f"{model_id}_unet.pth"

        filepath = self.models_dir / filename

        trainer_key = f'unet_{model_id}'
        if trainer_key in self._trainers:
            trainer = self._trainers[trainer_key]
            trainer.save_checkpoint(str(filepath))
        else:
            torch.save(self._unet_models[model_id].state_dict(), filepath)

        return {
            'model_id': model_id,
            'filepath': str(filepath),
            'status': 'saved'
        }

    def load_unet_model(
        self,
        model_id: str,
        filepath: str,
        in_channels: int = 1,
        out_channels: int = 1,
        base_channels: int = 64,
        depth: int = 4
    ) -> Dict[str, Any]:
        """
        Load U-Net model from disk.

        Args:
            model_id: Model identifier
            filepath: Path to model file
            in_channels: Input channels
            out_channels: Output channels
            base_channels: Base channels
            depth: Network depth

        Returns:
            Dictionary with load info
        """
        if not ML_IMPORTS_AVAILABLE:
            raise RuntimeError("ML modules not available")

        # Create model
        model = UNetGravity(
            in_channels=in_channels,
            out_channels=out_channels,
            base_channels=base_channels,
            depth=depth
        )

        # Load weights
        model.load_state_dict(torch.load(filepath, map_location=self.device))
        model.to(self.device)

        # Cache model
        self._unet_models[model_id] = model

        return {
            'model_id': model_id,
            'filepath': filepath,
            'status': 'loaded'
        }

    # =================================================================
    # Utility Methods
    # =================================================================

    def list_models(self) -> Dict[str, Any]:
        """List all loaded models."""
        return {
            'pinn_models': list(self._pinn_models.keys()),
            'unet_models': list(self._unet_models.keys()),
            'device': self.device
        }

    def _generate_pinn_data(self, n_samples: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate synthetic data for PINN training."""
        from ml.pinn import generate_synthetic_gravity_data
        coords, densities, gravity = generate_synthetic_gravity_data(n_samples=n_samples)
        return coords, densities, gravity

    def get_model_info(self, model_id: str, model_type: str = 'pinn') -> Dict[str, Any]:
        """
        Get information about a loaded model.

        Args:
            model_id: Model identifier
            model_type: 'pinn' or 'unet'

        Returns:
            Dictionary with model info
        """
        if model_type == 'pinn':
            if model_id not in self._pinn_models:
                raise ValueError(f"PINN model {model_id} not found")
            model = self._pinn_models[model_id]
        elif model_type == 'unet':
            if model_id not in self._unet_models:
                raise ValueError(f"UNet model {model_id} not found")
            model = self._unet_models[model_id]
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        n_params = sum(p.numel() for p in model.parameters())

        return {
            'model_id': model_id,
            'model_type': model_type,
            'n_parameters': n_params,
            'device': str(next(model.parameters()).device)
        }


# Singleton
_ml_service = None

def get_ml_service() -> MLService:
    """Get or create ML service singleton."""
    global _ml_service
    if _ml_service is None:
        _ml_service = MLService()
    return _ml_service
