"""
Inference Engine
================

Production inference utilities for deployed models.
"""

import numpy as np
from pathlib import Path
from typing import Optional, Union, Dict, List
import time

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:
    class ModelInference:
        """
        Inference engine for deployed models.
        
        Handles model loading, preprocessing, inference, and postprocessing.
        """
        
        def __init__(
            self,
            model_path: Union[str, Path],
            device: str = 'cpu',
            use_fp16: bool = False,
        ):
            """
            Args:
                model_path: Path to saved model
                device: Device for inference
                use_fp16: Use FP16 precision for faster inference
            """
            self.model_path = Path(model_path)
            self.device = torch.device(device)
            self.use_fp16 = use_fp16 and device == 'cuda'
            
            # Load model
            self.model = self.load_model()
            self.model.to(self.device)
            self.model.eval()
            
            if self.use_fp16:
                self.model.half()
        
        def load_model(self) -> nn.Module:
            """Load model from checkpoint."""
            checkpoint = torch.load(self.model_path, map_location=self.device)
            
            # Extract model state dict
            if 'model_state_dict' in checkpoint:
                state_dict = checkpoint['model_state_dict']
            else:
                state_dict = checkpoint
            
            # Load model architecture (placeholder - should be configurable)
            from ml.models.inversion import GravityInversionNN
            model = GravityInversionNN(
                n_gravity_obs=100,
                grid_shape=(32, 32),
            )
            model.load_state_dict(state_dict)
            
            return model
        
        def preprocess(self, data: np.ndarray) -> torch.Tensor:
            """
            Preprocess input data.
            
            Args:
                data: Raw input data
            
            Returns:
                Preprocessed tensor
            """
            # Convert to tensor
            tensor = torch.tensor(data, dtype=torch.float32)
            
            # Add batch dimension if needed
            if tensor.ndim == 1:
                tensor = tensor.unsqueeze(0)
            
            # Move to device
            tensor = tensor.to(self.device)
            
            # Convert to FP16 if needed
            if self.use_fp16:
                tensor = tensor.half()
            
            return tensor
        
        def postprocess(self, output: torch.Tensor) -> np.ndarray:
            """
            Postprocess model output.
            
            Args:
                output: Raw model output
            
            Returns:
                Processed numpy array
            """
            # Convert to float32 if FP16
            if self.use_fp16:
                output = output.float()
            
            # Move to CPU and convert to numpy
            return output.cpu().numpy()
        
        def predict(
            self,
            data: np.ndarray,
            return_uncertainty: bool = False,
        ) -> Union[np.ndarray, tuple]:
            """
            Run inference.
            
            Args:
                data: Input data
                return_uncertainty: Whether to return uncertainty estimates
            
            Returns:
                Predictions (and uncertainty if requested)
            """
            # Preprocess
            input_tensor = self.preprocess(data)
            
            # Inference
            with torch.no_grad():
                output = self.model(input_tensor)
            
            # Postprocess
            predictions = self.postprocess(output)
            
            if return_uncertainty:
                # Use dropout uncertainty
                self.model.train()
                n_samples = 50
                samples = []
                
                with torch.no_grad():
                    for _ in range(n_samples):
                        output = self.model(input_tensor)
                        samples.append(self.postprocess(output))
                
                samples = np.array(samples)
                uncertainty = np.std(samples, axis=0)
                
                self.model.eval()
                
                return predictions, uncertainty
            
            return predictions
        
        def benchmark(self, input_shape: tuple, n_iterations: int = 100) -> Dict[str, float]:
            """
            Benchmark inference performance.
            
            Args:
                input_shape: Shape of input data
                n_iterations: Number of iterations
            
            Returns:
                Performance metrics
            """
            # Generate random input
            dummy_input = torch.randn(input_shape).to(self.device)
            if self.use_fp16:
                dummy_input = dummy_input.half()
            
            # Warmup
            for _ in range(10):
                with torch.no_grad():
                    _ = self.model(dummy_input)
            
            # Benchmark
            start_time = time.time()
            
            for _ in range(n_iterations):
                with torch.no_grad():
                    _ = self.model(dummy_input)
            
            end_time = time.time()
            
            total_time = end_time - start_time
            avg_time = total_time / n_iterations
            throughput = 1.0 / avg_time
            
            return {
                'total_time_s': total_time,
                'avg_time_ms': avg_time * 1000,
                'throughput_fps': throughput,
            }
    
    
    class BatchInference:
        """
        Batch inference for processing large datasets.
        """
        
        def __init__(
            self,
            model: nn.Module,
            batch_size: int = 32,
            device: str = 'cpu',
        ):
            """
            Args:
                model: Neural network model
                batch_size: Batch size for inference
                device: Device for inference
            """
            self.model = model
            self.batch_size = batch_size
            self.device = torch.device(device)
            
            self.model.to(self.device)
            self.model.eval()
        
        def predict_batch(
            self,
            data: np.ndarray,
            show_progress: bool = True,
        ) -> np.ndarray:
            """
            Process data in batches.
            
            Args:
                data: Input data, shape (n_samples, ...)
                show_progress: Show progress bar
            
            Returns:
                Predictions for all samples
            """
            n_samples = data.shape[0]
            n_batches = (n_samples + self.batch_size - 1) // self.batch_size
            
            predictions = []
            
            for i in range(n_batches):
                start_idx = i * self.batch_size
                end_idx = min((i + 1) * self.batch_size, n_samples)
                
                batch = data[start_idx:end_idx]
                batch_tensor = torch.tensor(batch, dtype=torch.float32).to(self.device)
                
                with torch.no_grad():
                    batch_pred = self.model(batch_tensor)
                
                predictions.append(batch_pred.cpu().numpy())
                
                if show_progress:
                    print(f"Processed batch {i+1}/{n_batches}", end='\r')
            
            if show_progress:
                print()  # New line
            
            return np.concatenate(predictions, axis=0)
    
    
    class StreamingInference:
        """
        Streaming inference for real-time data.
        """
        
        def __init__(
            self,
            model: nn.Module,
            window_size: int = 100,
            device: str = 'cpu',
        ):
            """
            Args:
                model: Neural network model
                window_size: Size of sliding window
                device: Device for inference
            """
            self.model = model
            self.window_size = window_size
            self.device = torch.device(device)
            
            self.model.to(self.device)
            self.model.eval()
            
            self.buffer = []
        
        def process_sample(self, sample: np.ndarray) -> Optional[np.ndarray]:
            """
            Process incoming sample.
            
            Args:
                sample: New data sample
            
            Returns:
                Prediction when buffer is full, None otherwise
            """
            self.buffer.append(sample)
            
            if len(self.buffer) >= self.window_size:
                # Process window
                window = np.array(self.buffer[-self.window_size:])
                window_tensor = torch.tensor(window, dtype=torch.float32).unsqueeze(0).to(self.device)
                
                with torch.no_grad():
                    prediction = self.model(window_tensor)
                
                return prediction.cpu().numpy()
            
            return None
    
    
    def export_to_onnx(
        model: nn.Module,
        input_shape: tuple,
        output_path: Union[str, Path],
        opset_version: int = 11,
    ):
        """
        Export PyTorch model to ONNX format.
        
        Args:
            model: PyTorch model
            input_shape: Shape of input tensor
            output_path: Path to save ONNX model
            opset_version: ONNX opset version
        """
        model.eval()
        
        dummy_input = torch.randn(input_shape)
        
        torch.onnx.export(
            model,
            dummy_input,
            output_path,
            export_params=True,
            opset_version=opset_version,
            do_constant_folding=True,
            input_names=['input'],
            output_names=['output'],
            dynamic_axes={
                'input': {0: 'batch_size'},
                'output': {0: 'batch_size'},
            },
        )
        
        print(f"✓ Model exported to {output_path}")
    
    
    def load_from_onnx(model_path: Union[str, Path]):
        """
        Load model from ONNX format.
        
        Args:
            model_path: Path to ONNX model
        
        Returns:
            ONNX runtime session
        """
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError("onnxruntime required. Install with: pip install onnxruntime")
        
        session = ort.InferenceSession(str(model_path))
        
        print(f"✓ Model loaded from {model_path}")
        
        return session


else:
    # Fallback classes
    class ModelInference:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for inference")
    
    class BatchInference(ModelInference):
        pass
    
    class StreamingInference(ModelInference):
        pass
    
    def export_to_onnx(*args, **kwargs):
        raise ImportError("PyTorch required for ONNX export")
    
    def load_from_onnx(*args, **kwargs):
        raise ImportError("onnxruntime required for ONNX loading")
