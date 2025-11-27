"""
Uncertainty Quantification
===========================

Utilities for quantifying prediction uncertainty in geophysical inversions.
"""

import numpy as np
from typing import Optional, List, Tuple, Dict, Callable
from dataclasses import dataclass

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("Warning: PyTorch not available. ML module will not work.")


@dataclass
class UncertaintyEstimate:
    """Container for uncertainty estimates."""
    mean: np.ndarray
    std: np.ndarray
    lower_bound: np.ndarray
    upper_bound: np.ndarray
    epistemic_std: Optional[np.ndarray] = None
    aleatoric_std: Optional[np.ndarray] = None


if HAS_TORCH:
    def mc_dropout_predict(
        model: nn.Module,
        x: torch.Tensor,
        n_samples: int = 100,
        confidence_level: float = 0.95,
    ) -> UncertaintyEstimate:
        """
        Monte Carlo Dropout for uncertainty estimation.
        
        Enables dropout at test time to approximate Bayesian inference.
        
        Args:
            model: Neural network with dropout layers
            x: Input tensor
            n_samples: Number of MC samples
            confidence_level: Confidence level for intervals (0-1)
        
        Returns:
            UncertaintyEstimate with mean, std, and confidence intervals
        """
        model.train()  # Enable dropout
        
        predictions = []
        for _ in range(n_samples):
            with torch.no_grad():
                pred = model(x)
                predictions.append(pred)
        
        predictions = torch.stack(predictions, dim=0)  # (n_samples, batch, ...)
        
        # Compute statistics
        mean = predictions.mean(dim=0)
        std = predictions.std(dim=0)
        
        # Confidence intervals
        alpha = 1 - confidence_level
        z_score = torch.distributions.Normal(0, 1).icdf(torch.tensor(1 - alpha/2))
        lower_bound = mean - z_score * std
        upper_bound = mean + z_score * std
        
        model.eval()  # Disable dropout
        
        return UncertaintyEstimate(
            mean=mean.cpu().numpy(),
            std=std.cpu().numpy(),
            lower_bound=lower_bound.cpu().numpy(),
            upper_bound=upper_bound.cpu().numpy(),
            epistemic_std=std.cpu().numpy(),  # MC Dropout captures epistemic uncertainty
        )
    
    
    def ensemble_predict(
        models: List[nn.Module],
        x: torch.Tensor,
        confidence_level: float = 0.95,
    ) -> UncertaintyEstimate:
        """
        Ensemble prediction for uncertainty quantification.
        
        Args:
            models: List of trained models
            x: Input tensor
            confidence_level: Confidence level for intervals
        
        Returns:
            UncertaintyEstimate with ensemble statistics
        """
        predictions = []
        
        for model in models:
            model.eval()
            with torch.no_grad():
                pred = model(x)
                predictions.append(pred)
        
        predictions = torch.stack(predictions, dim=0)
        
        # Statistics
        mean = predictions.mean(dim=0)
        std = predictions.std(dim=0)
        
        # Confidence intervals
        alpha = 1 - confidence_level
        z_score = torch.distributions.Normal(0, 1).icdf(torch.tensor(1 - alpha/2))
        lower_bound = mean - z_score * std
        upper_bound = mean + z_score * std
        
        return UncertaintyEstimate(
            mean=mean.cpu().numpy(),
            std=std.cpu().numpy(),
            lower_bound=lower_bound.cpu().numpy(),
            upper_bound=upper_bound.cpu().numpy(),
            epistemic_std=std.cpu().numpy(),
        )
    
    
    class BayesianLinear(nn.Module):
        """
        Bayesian linear layer with variational inference.
        
        Uses Bayes by Backprop for weight uncertainty.
        """
        
        def __init__(self, in_features: int, out_features: int, prior_std: float = 1.0):
            super().__init__()
            
            self.in_features = in_features
            self.out_features = out_features
            
            # Weight mean and log variance
            self.weight_mu = nn.Parameter(torch.Tensor(out_features, in_features))
            self.weight_log_sigma = nn.Parameter(torch.Tensor(out_features, in_features))
            
            # Bias mean and log variance
            self.bias_mu = nn.Parameter(torch.Tensor(out_features))
            self.bias_log_sigma = nn.Parameter(torch.Tensor(out_features))
            
            # Prior
            self.prior_std = prior_std
            
            # Initialize
            self.reset_parameters()
        
        def reset_parameters(self):
            """Initialize parameters."""
            nn.init.normal_(self.weight_mu, mean=0, std=0.1)
            nn.init.constant_(self.weight_log_sigma, -3)  # Small initial variance
            nn.init.normal_(self.bias_mu, mean=0, std=0.1)
            nn.init.constant_(self.bias_log_sigma, -3)
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Forward pass with reparameterization trick.
            
            Args:
                x: Input tensor
            
            Returns:
                Output tensor
            """
            # Sample weights
            weight_sigma = torch.exp(self.weight_log_sigma)
            weight_eps = torch.randn_like(self.weight_mu)
            weight = self.weight_mu + weight_sigma * weight_eps
            
            # Sample bias
            bias_sigma = torch.exp(self.bias_log_sigma)
            bias_eps = torch.randn_like(self.bias_mu)
            bias = self.bias_mu + bias_sigma * bias_eps
            
            return F.linear(x, weight, bias)
        
        def kl_divergence(self) -> torch.Tensor:
            """
            KL divergence between posterior and prior.
            
            Returns:
                KL divergence scalar
            """
            # KL for weights
            weight_sigma = torch.exp(self.weight_log_sigma)
            kl_weight = torch.sum(
                self.weight_log_sigma - torch.log(torch.tensor(self.prior_std))
                + (weight_sigma**2 + self.weight_mu**2) / (2 * self.prior_std**2)
                - 0.5
            )
            
            # KL for bias
            bias_sigma = torch.exp(self.bias_log_sigma)
            kl_bias = torch.sum(
                self.bias_log_sigma - torch.log(torch.tensor(self.prior_std))
                + (bias_sigma**2 + self.bias_mu**2) / (2 * self.prior_std**2)
                - 0.5
            )
            
            return kl_weight + kl_bias
    
    
    class BayesianNN(nn.Module):
        """
        Bayesian Neural Network for uncertainty quantification.
        
        Uses variational inference to learn weight distributions.
        """
        
        def __init__(
            self,
            input_dim: int,
            output_dim: int,
            hidden_layers: List[int] = [128, 128],
            prior_std: float = 1.0,
        ):
            super().__init__()
            
            # Build Bayesian network
            layers = []
            prev_dim = input_dim
            
            for hidden_dim in hidden_layers:
                layers.append(BayesianLinear(prev_dim, hidden_dim, prior_std))
                layers.append(nn.ReLU())
                prev_dim = hidden_dim
            
            layers.append(BayesianLinear(prev_dim, output_dim, prior_std))
            
            self.layers = nn.ModuleList(layers)
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """Forward pass."""
            for layer in self.layers:
                x = layer(x)
            return x
        
        def kl_divergence(self) -> torch.Tensor:
            """Total KL divergence for all Bayesian layers."""
            kl = 0
            for layer in self.layers:
                if isinstance(layer, BayesianLinear):
                    kl += layer.kl_divergence()
            return kl
        
        def predict_with_uncertainty(
            self,
            x: torch.Tensor,
            n_samples: int = 100,
        ) -> Tuple[torch.Tensor, torch.Tensor]:
            """
            Predict with Bayesian uncertainty.
            
            Args:
                x: Input tensor
                n_samples: Number of samples from posterior
            
            Returns:
                Tuple of (mean, std)
            """
            self.train()  # Sample from posterior
            
            predictions = []
            for _ in range(n_samples):
                with torch.no_grad():
                    pred = self.forward(x)
                    predictions.append(pred)
            
            predictions = torch.stack(predictions, dim=0)
            
            mean = predictions.mean(dim=0)
            std = predictions.std(dim=0)
            
            self.eval()
            
            return mean, std
    
    
    def calibrate_uncertainty(
        predictions: np.ndarray,
        targets: np.ndarray,
        uncertainties: np.ndarray,
        n_bins: int = 10,
    ) -> Dict[str, np.ndarray]:
        """
        Calibration analysis for uncertainty estimates.
        
        Checks if predicted uncertainties match observed errors.
        
        Args:
            predictions: Model predictions, shape (n_samples,)
            targets: True values, shape (n_samples,)
            uncertainties: Predicted uncertainties (std), shape (n_samples,)
            n_bins: Number of calibration bins
        
        Returns:
            Dictionary with calibration metrics
        """
        # Compute normalized errors
        errors = np.abs(predictions - targets)
        normalized_errors = errors / (uncertainties + 1e-8)
        
        # Bin by predicted uncertainty
        bin_edges = np.linspace(0, uncertainties.max(), n_bins + 1)
        bin_indices = np.digitize(uncertainties, bin_edges) - 1
        
        # Compute calibration metrics per bin
        expected_errors = []
        observed_errors = []
        bin_counts = []
        
        for i in range(n_bins):
            mask = bin_indices == i
            if mask.sum() > 0:
                expected_errors.append(bin_edges[i:i+2].mean())
                observed_errors.append(errors[mask].mean())
                bin_counts.append(mask.sum())
            else:
                expected_errors.append(bin_edges[i:i+2].mean())
                observed_errors.append(np.nan)
                bin_counts.append(0)
        
        # Expected Calibration Error (ECE)
        ece = 0
        total_count = len(predictions)
        for i in range(n_bins):
            if bin_counts[i] > 0:
                ece += (bin_counts[i] / total_count) * abs(expected_errors[i] - observed_errors[i])
        
        return {
            'expected_errors': np.array(expected_errors),
            'observed_errors': np.array(observed_errors),
            'bin_counts': np.array(bin_counts),
            'ece': ece,
            'normalized_errors': normalized_errors,
        }
    
    
    def prediction_interval_coverage(
        targets: np.ndarray,
        lower_bounds: np.ndarray,
        upper_bounds: np.ndarray,
    ) -> float:
        """
        Compute prediction interval coverage probability.
        
        Measures fraction of targets within predicted intervals.
        
        Args:
            targets: True values
            lower_bounds: Lower confidence bounds
            upper_bounds: Upper confidence bounds
        
        Returns:
            Coverage probability (0-1)
        """
        within_interval = (targets >= lower_bounds) & (targets <= upper_bounds)
        return within_interval.mean()
    
    
    def decompose_uncertainty(
        model: nn.Module,
        x: torch.Tensor,
        n_epistemic_samples: int = 50,
        n_aleatoric_samples: int = 50,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Decompose uncertainty into epistemic and aleatoric components.
        
        Epistemic: Model uncertainty (reducible with more data)
        Aleatoric: Data uncertainty (irreducible noise)
        
        Args:
            model: Neural network with dropout
            x: Input tensor
            n_epistemic_samples: MC samples for epistemic uncertainty
            n_aleatoric_samples: Samples for aleatoric uncertainty per epistemic sample
        
        Returns:
            Tuple of (total_uncertainty, epistemic_uncertainty, aleatoric_uncertainty)
        """
        model.train()
        
        epistemic_predictions = []
        aleatoric_vars = []
        
        for _ in range(n_epistemic_samples):
            # Sample from epistemic distribution (dropout)
            preds = []
            for _ in range(n_aleatoric_samples):
                with torch.no_grad():
                    pred = model(x)
                    preds.append(pred)
            
            preds = torch.stack(preds, dim=0)
            epistemic_predictions.append(preds.mean(dim=0))
            aleatoric_vars.append(preds.var(dim=0))
        
        epistemic_predictions = torch.stack(epistemic_predictions, dim=0)
        aleatoric_vars = torch.stack(aleatoric_vars, dim=0)
        
        # Epistemic uncertainty (variance of means)
        epistemic_uncertainty = epistemic_predictions.var(dim=0)
        
        # Aleatoric uncertainty (mean of variances)
        aleatoric_uncertainty = aleatoric_vars.mean(dim=0)
        
        # Total uncertainty
        total_uncertainty = epistemic_uncertainty + aleatoric_uncertainty
        
        model.eval()
        
        return (
            torch.sqrt(total_uncertainty),
            torch.sqrt(epistemic_uncertainty),
            torch.sqrt(aleatoric_uncertainty),
        )
    
    
    class DeepEnsemble:
        """
        Deep ensemble for robust uncertainty quantification.
        
        Trains multiple models with different initializations and combines predictions.
        """
        
        def __init__(self, models: List[nn.Module]):
            """
            Args:
                models: List of neural network models
            """
            self.models = models
            self.n_models = len(models)
        
        def predict(
            self,
            x: torch.Tensor,
            return_individual: bool = False,
        ) -> torch.Tensor:
            """
            Ensemble prediction.
            
            Args:
                x: Input tensor
                return_individual: If True, return all individual predictions
            
            Returns:
                Mean prediction or all predictions if return_individual=True
            """
            predictions = []
            
            for model in self.models:
                model.eval()
                with torch.no_grad():
                    pred = model(x)
                    predictions.append(pred)
            
            predictions = torch.stack(predictions, dim=0)
            
            if return_individual:
                return predictions
            else:
                return predictions.mean(dim=0)
        
        def predict_with_uncertainty(
            self,
            x: torch.Tensor,
            confidence_level: float = 0.95,
        ) -> UncertaintyEstimate:
            """
            Predict with ensemble uncertainty.
            
            Args:
                x: Input tensor
                confidence_level: Confidence level for intervals
            
            Returns:
                UncertaintyEstimate
            """
            predictions = self.predict(x, return_individual=True)
            
            mean = predictions.mean(dim=0)
            std = predictions.std(dim=0)
            
            # Confidence intervals
            alpha = 1 - confidence_level
            z_score = torch.distributions.Normal(0, 1).icdf(torch.tensor(1 - alpha/2))
            lower_bound = mean - z_score * std
            upper_bound = mean + z_score * std
            
            return UncertaintyEstimate(
                mean=mean.cpu().numpy(),
                std=std.cpu().numpy(),
                lower_bound=lower_bound.cpu().numpy(),
                upper_bound=upper_bound.cpu().numpy(),
                epistemic_std=std.cpu().numpy(),
            )


else:
    # Fallback if PyTorch not available
    def mc_dropout_predict(*args, **kwargs):
        raise ImportError("PyTorch required for uncertainty quantification")
    
    def ensemble_predict(*args, **kwargs):
        raise ImportError("PyTorch required for uncertainty quantification")
    
    class BayesianLinear:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for Bayesian layers")
    
    class BayesianNN(BayesianLinear):
        pass
    
    class DeepEnsemble:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for ensembles")
    
    def calibrate_uncertainty(*args, **kwargs):
        raise ImportError("PyTorch required for calibration")
    
    def prediction_interval_coverage(*args, **kwargs):
        raise ImportError("PyTorch required for coverage analysis")
    
    def decompose_uncertainty(*args, **kwargs):
        raise ImportError("PyTorch required for uncertainty decomposition")
