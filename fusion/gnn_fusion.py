"""
Graph Neural Network (GNN) Based Fusion
========================================

GNN for fusing heterogeneous multi-sensor geophysical data.
"""

import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass
import warnings

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    warnings.warn("PyTorch not available, GNN fusion will not work")


@dataclass
class GraphData:
    """
    Graph representation of geophysical data.

    Attributes:
        node_features: Node feature matrix, shape (n_nodes, n_features)
        edge_index: Edge connectivity, shape (2, n_edges)
        edge_attr: Edge attributes (optional), shape (n_edges, n_edge_features)
        labels: Ground truth (for training), shape (n_nodes,)
    """
    node_features: np.ndarray
    edge_index: np.ndarray
    edge_attr: Optional[np.ndarray] = None
    labels: Optional[np.ndarray] = None


if HAS_TORCH:
    class GraphConvLayer(nn.Module):
        """
        Graph Convolutional Layer.

        Aggregates neighbor information using message passing.
        """

        def __init__(self, in_features: int, out_features: int):
            super().__init__()
            self.linear = nn.Linear(in_features, out_features)

        def forward(
            self,
            x: torch.Tensor,
            edge_index: torch.Tensor,
        ) -> torch.Tensor:
            """
            Forward pass.

            Args:
                x: Node features, shape (n_nodes, in_features)
                edge_index: Edge connectivity, shape (2, n_edges)

            Returns:
                Updated node features, shape (n_nodes, out_features)
            """
            # Transform features
            x_transformed = self.linear(x)

            # Aggregate messages from neighbors
            row, col = edge_index
            n_nodes = x.shape[0]

            # Message passing: aggregate neighbor features
            messages = torch.zeros_like(x_transformed)

            for i in range(edge_index.shape[1]):
                src, dst = row[i].item(), col[i].item()
                messages[dst] += x_transformed[src]

            # Normalize by degree
            degree = torch.zeros(n_nodes, device=x.device)
            for i in range(edge_index.shape[1]):
                dst = col[i].item()
                degree[dst] += 1

            degree = torch.clamp(degree, min=1.0)  # Avoid division by zero
            messages = messages / degree.unsqueeze(1)

            return messages


    class GNNFusionModel(nn.Module):
        """
        GNN model for multi-sensor data fusion.

        Architecture:
        - Multiple graph convolutional layers
        - Skip connections
        - Layer normalization
        - Final prediction layer
        """

        def __init__(
            self,
            in_features: int,
            hidden_dim: int = 64,
            out_features: int = 1,
            n_layers: int = 3,
            dropout: float = 0.1,
        ):
            """
            Args:
                in_features: Number of input features per node
                hidden_dim: Hidden dimension
                out_features: Output dimension (1 for regression)
                n_layers: Number of GNN layers
                dropout: Dropout probability
            """
            super().__init__()

            self.n_layers = n_layers

            # Input projection
            self.input_proj = nn.Linear(in_features, hidden_dim)

            # GNN layers
            self.conv_layers = nn.ModuleList([
                GraphConvLayer(hidden_dim, hidden_dim)
                for _ in range(n_layers)
            ])

            # Layer normalization
            self.layer_norms = nn.ModuleList([
                nn.LayerNorm(hidden_dim)
                for _ in range(n_layers)
            ])

            # Dropout
            self.dropout = nn.Dropout(dropout)

            # Output projection
            self.output_proj = nn.Linear(hidden_dim, out_features)

        def forward(
            self,
            x: torch.Tensor,
            edge_index: torch.Tensor,
        ) -> torch.Tensor:
            """
            Forward pass.

            Args:
                x: Node features, shape (n_nodes, in_features)
                edge_index: Edge connectivity, shape (2, n_edges)

            Returns:
                Predictions, shape (n_nodes, out_features)
            """
            # Input projection
            h = self.input_proj(x)
            h = F.relu(h)

            # GNN layers with residual connections
            for i in range(self.n_layers):
                h_new = self.conv_layers[i](h, edge_index)
                h_new = self.layer_norms[i](h_new)
                h_new = F.relu(h_new)
                h_new = self.dropout(h_new)

                # Residual connection
                h = h + h_new

            # Output
            out = self.output_proj(h)

            return out


    class MultiModalGNNFusion:
        """
        Multi-modal GNN fusion for gravity + magnetics + seismic.
        """

        def __init__(
            self,
            n_gravity_features: int,
            n_magnetic_features: int,
            n_seismic_features: int = 0,
            hidden_dim: int = 64,
            n_layers: int = 3,
        ):
            """
            Args:
                n_gravity_features: Number of gravity-related features
                n_magnetic_features: Number of magnetic features
                n_seismic_features: Number of seismic features
                hidden_dim: Hidden dimension
                n_layers: Number of GNN layers
            """
            self.n_gravity = n_gravity_features
            self.n_magnetic = n_magnetic_features
            self.n_seismic = n_seismic_features

            total_features = n_gravity_features + n_magnetic_features + n_seismic_features

            self.model = GNNFusionModel(
                in_features=total_features,
                hidden_dim=hidden_dim,
                out_features=1,
                n_layers=n_layers,
            )

            self.optimizer = None
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            self.model.to(self.device)

        def prepare_graph(
            self,
            gravity_data: np.ndarray,
            magnetic_data: np.ndarray,
            seismic_data: Optional[np.ndarray] = None,
            spatial_coords: np.ndarray = None,
            k_neighbors: int = 8,
        ) -> GraphData:
            """
            Convert multi-modal data to graph representation.

            Args:
                gravity_data: Gravity observations, shape (n_points, n_grav_features)
                magnetic_data: Magnetic observations, shape (n_points, n_mag_features)
                seismic_data: Seismic observations (optional)
                spatial_coords: Spatial coordinates, shape (n_points, 2 or 3)
                k_neighbors: Number of neighbors for graph construction

            Returns:
                GraphData object
            """
            n_points = gravity_data.shape[0]

            # Concatenate features
            features = [gravity_data, magnetic_data]
            if seismic_data is not None:
                features.append(seismic_data)

            node_features = np.hstack(features)

            # Build graph edges (k-nearest neighbors)
            if spatial_coords is not None:
                edge_index = self._build_knn_graph(spatial_coords, k_neighbors)
            else:
                # Fallback: grid graph
                edge_index = self._build_grid_graph(n_points)

            return GraphData(
                node_features=node_features,
                edge_index=edge_index,
            )

        def _build_knn_graph(
            self,
            coords: np.ndarray,
            k: int,
        ) -> np.ndarray:
            """
            Build k-nearest neighbor graph.

            Args:
                coords: Spatial coordinates, shape (n, d)
                k: Number of neighbors

            Returns:
                Edge index, shape (2, n_edges)
            """
            from scipy.spatial import KDTree

            n = coords.shape[0]

            # Build KD-tree
            tree = KDTree(coords)

            # Find k nearest neighbors
            edges = []
            for i in range(n):
                _, indices = tree.query(coords[i], k=k+1)  # +1 to exclude self
                for j in indices[1:]:  # Skip self
                    edges.append([i, j])

            edge_index = np.array(edges).T

            return edge_index

        def _build_grid_graph(self, n_points: int) -> np.ndarray:
            """
            Build simple grid graph (4-connectivity).

            Args:
                n_points: Number of points (assumed square grid)

            Returns:
                Edge index, shape (2, n_edges)
            """
            n = int(np.sqrt(n_points))
            edges = []

            for i in range(n):
                for j in range(n):
                    idx = i * n + j

                    # Right neighbor
                    if j < n - 1:
                        edges.append([idx, idx + 1])

                    # Bottom neighbor
                    if i < n - 1:
                        edges.append([idx, idx + n])

            edge_index = np.array(edges).T

            # Make undirected
            edge_index = np.hstack([edge_index, edge_index[::-1]])

            return edge_index

        def train(
            self,
            graph_data: GraphData,
            labels: np.ndarray,
            n_epochs: int = 100,
            learning_rate: float = 1e-3,
            weight_decay: float = 1e-4,
        ) -> List[float]:
            """
            Train GNN model.

            Args:
                graph_data: Graph data
                labels: Ground truth, shape (n_nodes,)
                n_epochs: Number of training epochs
                learning_rate: Learning rate
                weight_decay: L2 regularization

            Returns:
                List of training losses
            """
            # Convert to PyTorch tensors
            x = torch.tensor(graph_data.node_features, dtype=torch.float32).to(self.device)
            edge_index = torch.tensor(graph_data.edge_index, dtype=torch.long).to(self.device)
            y = torch.tensor(labels, dtype=torch.float32).unsqueeze(1).to(self.device)

            # Optimizer
            self.optimizer = torch.optim.Adam(
                self.model.parameters(),
                lr=learning_rate,
                weight_decay=weight_decay,
            )

            # Training loop
            losses = []
            self.model.train()

            for epoch in range(n_epochs):
                self.optimizer.zero_grad()

                # Forward pass
                pred = self.model(x, edge_index)

                # Loss
                loss = F.mse_loss(pred, y)

                # Backward pass
                loss.backward()
                self.optimizer.step()

                losses.append(loss.item())

                if (epoch + 1) % 10 == 0:
                    print(f"Epoch {epoch+1}/{n_epochs}, Loss: {loss.item():.6f}")

            return losses

        def predict(self, graph_data: GraphData) -> np.ndarray:
            """
            Make predictions using trained model.

            Args:
                graph_data: Graph data

            Returns:
                Predictions, shape (n_nodes,)
            """
            self.model.eval()

            with torch.no_grad():
                x = torch.tensor(graph_data.node_features, dtype=torch.float32).to(self.device)
                edge_index = torch.tensor(graph_data.edge_index, dtype=torch.long).to(self.device)

                pred = self.model(x, edge_index)

            return pred.cpu().numpy().squeeze()


# Fallback if PyTorch not available
else:
    class MultiModalGNNFusion:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for GNN fusion. Install with: pip install torch")
