"""
Model Optimization
==================

Tools for model quantization, pruning, and optimization for edge deployment.
"""

import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple, Dict

try:
    import torch
    import torch.nn as nn
    import torch.quantization as quant
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:
    class ModelQuantizer:
        """
        Model quantization for reduced model size and faster inference.
        
        Converts FP32 models to INT8.
        """
        
        def __init__(self, model: nn.Module):
            """
            Args:
                model: PyTorch model to quantize
            """
            self.model = model
        
        def dynamic_quantize(self) -> nn.Module:
            """
            Dynamic quantization (fastest, no calibration needed).
            
            Returns:
                Quantized model
            """
            quantized_model = quant.quantize_dynamic(
                self.model,
                {nn.Linear, nn.Conv2d, nn.Conv3d},
                dtype=torch.qint8,
            )
            
            print("✓ Dynamic quantization complete")
            return quantized_model
        
        def static_quantize(
            self,
            calibration_loader,
            device: str = 'cpu',
        ) -> nn.Module:
            """
            Static quantization (better accuracy, requires calibration).
            
            Args:
                calibration_loader: DataLoader with calibration data
                device: Device for calibration
            
            Returns:
                Quantized model
            """
            # Prepare model for quantization
            self.model.eval()
            self.model.to(device)
            
            # Fuse modules (Conv+BN+ReLU)
            self.model = quant.fuse_modules(
                self.model,
                [['0', '1', '2']],  # Example: adjust based on model architecture
            )
            
            # Attach quantization config
            self.model.qconfig = quant.get_default_qconfig('fbgemm')
            
            # Prepare
            quant.prepare(self.model, inplace=True)
            
            # Calibration
            print("Running calibration...")
            with torch.no_grad():
                for batch in calibration_loader:
                    if isinstance(batch, (list, tuple)):
                        data = batch[0].to(device)
                    else:
                        data = batch.to(device)
                    
                    self.model(data)
            
            # Convert to quantized model
            quantized_model = quant.convert(self.model, inplace=False)
            
            print("✓ Static quantization complete")
            return quantized_model
        
        def quantization_aware_training(
            self,
            train_loader,
            loss_fn,
            n_epochs: int = 10,
            learning_rate: float = 1e-4,
            device: str = 'cpu',
        ) -> nn.Module:
            """
            Quantization-aware training (best accuracy).
            
            Args:
                train_loader: Training data
                loss_fn: Loss function
                n_epochs: Number of epochs
                learning_rate: Learning rate
                device: Device for training
            
            Returns:
                Quantized model
            """
            self.model.train()
            self.model.to(device)
            
            # Attach quantization config
            self.model.qconfig = quant.get_default_qat_qconfig('fbgemm')
            
            # Prepare for QAT
            quant.prepare_qat(self.model, inplace=True)
            
            # Train
            optimizer = torch.optim.Adam(self.model.parameters(), lr=learning_rate)
            
            print("Quantization-aware training...")
            for epoch in range(n_epochs):
                epoch_loss = 0
                n_batches = 0
                
                for batch in train_loader:
                    if isinstance(batch, (list, tuple)):
                        data, target = batch[0].to(device), batch[1].to(device)
                    else:
                        data = batch.to(device)
                        target = None
                    
                    optimizer.zero_grad()
                    output = self.model(data)
                    
                    if target is not None:
                        loss = loss_fn(output, target)
                    else:
                        loss = loss_fn(output)
                    
                    loss.backward()
                    optimizer.step()
                    
                    epoch_loss += loss.item()
                    n_batches += 1
                
                avg_loss = epoch_loss / n_batches
                print(f"Epoch {epoch+1}/{n_epochs}, Loss: {avg_loss:.6f}")
            
            # Convert to quantized model
            self.model.eval()
            quantized_model = quant.convert(self.model, inplace=False)
            
            print("✓ Quantization-aware training complete")
            return quantized_model
        
        @staticmethod
        def measure_model_size(model: nn.Module) -> Dict[str, float]:
            """
            Measure model size.
            
            Args:
                model: PyTorch model
            
            Returns:
                Dictionary with size metrics
            """
            # Save to buffer
            import io
            buffer = io.BytesIO()
            torch.save(model.state_dict(), buffer)
            size_bytes = buffer.tell()
            
            # Count parameters
            n_params = sum(p.numel() for p in model.parameters())
            
            return {
                'size_mb': size_bytes / (1024 * 1024),
                'size_kb': size_bytes / 1024,
                'n_parameters': n_params,
            }
    
    
    class ModelPruner:
        """
        Model pruning to reduce parameters.
        
        Removes less important weights to reduce model size.
        """
        
        def __init__(self, model: nn.Module):
            """
            Args:
                model: PyTorch model to prune
            """
            self.model = model
        
        def magnitude_prune(
            self,
            amount: float = 0.3,
            layers_to_prune: Optional[List[str]] = None,
        ) -> nn.Module:
            """
            Magnitude-based pruning.
            
            Args:
                amount: Fraction of weights to prune (0-1)
                layers_to_prune: List of layer names to prune (None = all Linear/Conv)
            
            Returns:
                Pruned model
            """
            import torch.nn.utils.prune as prune
            
            # Identify layers to prune
            if layers_to_prune is None:
                layers_to_prune = [
                    (name, module) for name, module in self.model.named_modules()
                    if isinstance(module, (nn.Linear, nn.Conv2d, nn.Conv3d))
                ]
            else:
                layers_to_prune = [
                    (name, module) for name, module in self.model.named_modules()
                    if name in layers_to_prune
                ]
            
            # Apply pruning
            for name, module in layers_to_prune:
                prune.l1_unstructured(module, name='weight', amount=amount)
            
            print(f"✓ Magnitude pruning complete ({amount*100:.1f}% weights removed)")
            return self.model
        
        def structured_prune(
            self,
            amount: float = 0.3,
            dim: int = 0,
        ) -> nn.Module:
            """
            Structured pruning (removes entire channels/neurons).
            
            Args:
                amount: Fraction of channels to prune
                dim: Dimension to prune (0=output, 1=input)
            
            Returns:
                Pruned model
            """
            import torch.nn.utils.prune as prune
            
            for name, module in self.model.named_modules():
                if isinstance(module, (nn.Linear, nn.Conv2d, nn.Conv3d)):
                    prune.ln_structured(
                        module,
                        name='weight',
                        amount=amount,
                        n=2,
                        dim=dim,
                    )
            
            print(f"✓ Structured pruning complete ({amount*100:.1f}% channels removed)")
            return self.model
        
        def iterative_prune(
            self,
            train_loader,
            loss_fn,
            initial_amount: float = 0.2,
            n_iterations: int = 5,
            finetune_epochs: int = 2,
        ) -> nn.Module:
            """
            Iterative pruning with fine-tuning.
            
            Gradually prune and fine-tune for better accuracy.
            
            Args:
                train_loader: Training data
                loss_fn: Loss function
                initial_amount: Initial pruning amount
                n_iterations: Number of prune-finetune iterations
                finetune_epochs: Epochs to fine-tune after each prune
            
            Returns:
                Pruned and fine-tuned model
            """
            import torch.nn.utils.prune as prune
            
            optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-4)
            
            for iteration in range(n_iterations):
                print(f"\nIteration {iteration+1}/{n_iterations}")
                
                # Prune
                amount = initial_amount
                for module in self.model.modules():
                    if isinstance(module, (nn.Linear, nn.Conv2d)):
                        prune.l1_unstructured(module, name='weight', amount=amount)
                
                # Fine-tune
                self.model.train()
                for epoch in range(finetune_epochs):
                    for batch in train_loader:
                        optimizer.zero_grad()
                        
                        if isinstance(batch, (list, tuple)):
                            data, target = batch
                        else:
                            data, target = batch, None
                        
                        output = self.model(data)
                        loss = loss_fn(output, target) if target is not None else loss_fn(output)
                        
                        loss.backward()
                        optimizer.step()
            
            print("✓ Iterative pruning complete")
            return self.model
        
        def make_permanent(self) -> nn.Module:
            """
            Make pruning permanent by removing pruning masks.
            
            Returns:
                Model with permanently pruned weights
            """
            import torch.nn.utils.prune as prune
            
            for module in self.model.modules():
                if isinstance(module, (nn.Linear, nn.Conv2d, nn.Conv3d)):
                    if hasattr(module, 'weight_mask'):
                        prune.remove(module, 'weight')
            
            return self.model
    
    
    class ModelOptimizer:
        """
        Combined optimization pipeline.
        
        Applies pruning + quantization for maximum compression.
        """
        
        def __init__(self, model: nn.Module):
            """
            Args:
                model: PyTorch model
            """
            self.model = model
            self.pruner = ModelPruner(model)
            self.quantizer = ModelQuantizer(model)
        
        def optimize(
            self,
            prune_amount: float = 0.5,
            use_quantization: bool = True,
            calibration_loader = None,
        ) -> Tuple[nn.Module, Dict[str, float]]:
            """
            Full optimization pipeline.
            
            Args:
                prune_amount: Fraction of weights to prune
                use_quantization: Whether to apply quantization
                calibration_loader: Data for quantization calibration
            
            Returns:
                Tuple of (optimized_model, metrics)
            """
            # Original metrics
            original_size = ModelQuantizer.measure_model_size(self.model)
            
            # Step 1: Pruning
            print("Step 1: Pruning...")
            self.model = self.pruner.magnitude_prune(amount=prune_amount)
            self.model = self.pruner.make_permanent()
            
            pruned_size = ModelQuantizer.measure_model_size(self.model)
            
            # Step 2: Quantization
            if use_quantization:
                print("\nStep 2: Quantization...")
                if calibration_loader is not None:
                    self.model = self.quantizer.static_quantize(calibration_loader)
                else:
                    self.model = self.quantizer.dynamic_quantize()
            
            final_size = ModelQuantizer.measure_model_size(self.model)
            
            # Compute metrics
            metrics = {
                'original_size_mb': original_size['size_mb'],
                'final_size_mb': final_size['size_mb'],
                'compression_ratio': original_size['size_mb'] / final_size['size_mb'],
                'size_reduction_percent': (1 - final_size['size_mb'] / original_size['size_mb']) * 100,
            }
            
            print(f"\n✓ Optimization complete!")
            print(f"  Original size: {metrics['original_size_mb']:.2f} MB")
            print(f"  Final size: {metrics['final_size_mb']:.2f} MB")
            print(f"  Compression: {metrics['compression_ratio']:.2f}x")
            print(f"  Size reduction: {metrics['size_reduction_percent']:.1f}%")
            
            return self.model, metrics


else:
    # Fallback classes
    class ModelQuantizer:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for quantization")
    
    class ModelPruner(ModelQuantizer):
        pass
    
    class ModelOptimizer(ModelQuantizer):
        pass
