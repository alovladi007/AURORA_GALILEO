"""
Model Serving
=============

REST API server for model deployment.
"""

import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any
import json

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class ModelServer:
    """
    Simple model server for inference.
    """
    
    def __init__(
        self,
        model_path: str,
        device: str = 'cpu',
    ):
        """
        Args:
            model_path: Path to saved model
            device: Device for inference
        """
        if HAS_TORCH:
            from .inference import ModelInference
            self.inference_engine = ModelInference(model_path, device)
        else:
            raise ImportError("PyTorch required for model serving")
    
    def predict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run prediction.
        
        Args:
            data: Input data dictionary with 'observations' key
        
        Returns:
            Dictionary with 'predictions' and metadata
        """
        observations = np.array(data['observations'])
        
        # Run inference
        predictions = self.inference_engine.predict(observations)
        
        return {
            'predictions': predictions.tolist(),
            'shape': predictions.shape,
            'dtype': str(predictions.dtype),
        }
    
    def health_check(self) -> Dict[str, str]:
        """Health check endpoint."""
        return {
            'status': 'healthy',
            'model_loaded': True,
        }


class RESTAPIServer:
    """
    REST API server using FastAPI.
    
    Requires: pip install fastapi uvicorn
    """
    
    def __init__(
        self,
        model_path: str,
        host: str = '0.0.0.0',
        port: int = 8000,
    ):
        """
        Args:
            model_path: Path to model
            host: Server host
            port: Server port
        """
        self.model_path = model_path
        self.host = host
        self.port = port
        self.server = ModelServer(model_path)
    
    def create_app(self):
        """Create FastAPI application."""
        try:
            from fastapi import FastAPI, HTTPException
            from pydantic import BaseModel
        except ImportError:
            raise ImportError("FastAPI required. Install with: pip install fastapi uvicorn")
        
        app = FastAPI(title="GALILEO ML Inference API")
        
        class PredictionRequest(BaseModel):
            observations: list
        
        class PredictionResponse(BaseModel):
            predictions: list
            shape: list
            dtype: str
        
        @app.post("/predict", response_model=PredictionResponse)
        def predict(request: PredictionRequest):
            """Prediction endpoint."""
            try:
                data = {'observations': request.observations}
                result = self.server.predict(data)
                return result
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.get("/health")
        def health():
            """Health check endpoint."""
            return self.server.health_check()
        
        @app.get("/")
        def root():
            """Root endpoint."""
            return {
                'name': 'GALILEO ML Inference API',
                'version': '2.0.0',
                'endpoints': ['/predict', '/health'],
            }
        
        return app
    
    def run(self):
        """Run server."""
        try:
            import uvicorn
        except ImportError:
            raise ImportError("uvicorn required. Install with: pip install uvicorn")
        
        app = self.create_app()
        uvicorn.run(app, host=self.host, port=self.port)


def create_fastapi_app(model_path: str):
    """
    Create FastAPI application for model serving.
    
    Args:
        model_path: Path to saved model
    
    Returns:
        FastAPI application
    
    Example:
        >>> app = create_fastapi_app('model.pt')
        >>> # Run with: uvicorn main:app --reload
    """
    server = RESTAPIServer(model_path)
    return server.create_app()


# Example deployment script
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='GALILEO ML Inference Server')
    parser.add_argument('--model', type=str, required=True, help='Path to model file')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host address')
    parser.add_argument('--port', type=int, default=8000, help='Port number')
    parser.add_argument('--device', type=str, default='cpu', help='Device (cpu/cuda)')
    
    args = parser.parse_args()
    
    print(f"Starting GALILEO ML Inference Server...")
    print(f"Model: {args.model}")
    print(f"Host: {args.host}:{args.port}")
    print(f"Device: {args.device}")
    
    server = RESTAPIServer(args.model, host=args.host, port=args.port)
    server.run()
