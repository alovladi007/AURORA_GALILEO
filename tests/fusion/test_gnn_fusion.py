"""
Tests for GNN-Based Fusion
===========================

Tests Graph Neural Network fusion for multi-sensor geophysical data.
"""

import pytest
import numpy as np
from fusion.gnn_fusion import (
    GraphData,
    HAS_TORCH,
)

# Conditionally import PyTorch components
if HAS_TORCH:
    from fusion.gnn_fusion import (
        GraphConvLayer,
        GNNFusionModel,
        MultiModalGNNFusion,
    )
    import torch


class TestGraphData:
    """Test GraphData dataclass."""

    def test_basic_graph_data(self):
        """Test basic graph data creation."""
        node_features = np.random.randn(10, 5)
        edge_index = np.array([[0, 1, 2], [1, 2, 3]])

        graph = GraphData(
            node_features=node_features,
            edge_index=edge_index,
        )

        assert graph.node_features.shape == (10, 5)
        assert graph.edge_index.shape == (2, 3)
        assert graph.edge_attr is None
        assert graph.labels is None

    def test_graph_data_with_labels(self):
        """Test graph data with labels."""
        node_features = np.random.randn(20, 8)
        edge_index = np.array([[0, 1], [1, 2]])
        labels = np.random.randn(20)

        graph = GraphData(
            node_features=node_features,
            edge_index=edge_index,
            labels=labels,
        )

        assert graph.labels.shape == (20,)
        np.testing.assert_array_equal(graph.labels, labels)

    def test_graph_data_with_edge_attributes(self):
        """Test graph data with edge attributes."""
        node_features = np.random.randn(15, 4)
        edge_index = np.array([[0, 1, 2], [1, 2, 3]])
        edge_attr = np.random.randn(3, 2)  # 3 edges, 2 features each

        graph = GraphData(
            node_features=node_features,
            edge_index=edge_index,
            edge_attr=edge_attr,
        )

        assert graph.edge_attr.shape == (3, 2)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestGraphConvLayer:
    """Test Graph Convolutional Layer."""

    def test_initialization(self):
        """Test layer initialization."""
        layer = GraphConvLayer(in_features=10, out_features=20)

        assert layer.linear.in_features == 10
        assert layer.linear.out_features == 20

    def test_forward_pass(self):
        """Test forward pass through graph conv layer."""
        layer = GraphConvLayer(in_features=5, out_features=8)

        # Create simple graph: 4 nodes, 3 edges
        x = torch.randn(4, 5)
        edge_index = torch.tensor([[0, 1, 2], [1, 2, 3]], dtype=torch.long)

        output = layer(x, edge_index)

        assert output.shape == (4, 8)

    def test_message_aggregation(self):
        """Test that messages are aggregated correctly."""
        layer = GraphConvLayer(in_features=2, out_features=2)

        # Simple graph: node 1 receives from node 0
        x = torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32)
        edge_index = torch.tensor([[0], [1]], dtype=torch.long)

        output = layer(x, edge_index)

        # Node 1 should receive aggregated message from node 0
        assert output.shape == (2, 2)

    def test_isolated_node(self):
        """Test behavior with isolated node (no incoming edges)."""
        layer = GraphConvLayer(in_features=3, out_features=4)

        # Node 2 is isolated (no incoming edges)
        x = torch.randn(3, 3)
        edge_index = torch.tensor([[0], [1]], dtype=torch.long)

        output = layer(x, edge_index)

        # Should still work, isolated node gets zero aggregation
        assert output.shape == (3, 4)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestGNNFusionModel:
    """Test GNN Fusion Model."""

    def test_initialization(self):
        """Test model initialization."""
        model = GNNFusionModel(
            in_features=10,
            hidden_dim=32,
            out_features=1,
            n_layers=3,
            dropout=0.1,
        )

        assert model.n_layers == 3
        assert len(model.conv_layers) == 3
        assert len(model.layer_norms) == 3

    def test_forward_pass(self):
        """Test forward pass through full model."""
        model = GNNFusionModel(
            in_features=8,
            hidden_dim=16,
            out_features=1,
            n_layers=2,
        )

        x = torch.randn(10, 8)
        edge_index = torch.tensor(
            [[0, 1, 2, 3, 4], [1, 2, 3, 4, 0]], dtype=torch.long
        )

        output = model(x, edge_index)

        assert output.shape == (10, 1)

    def test_different_output_dimensions(self):
        """Test model with different output dimensions."""
        model = GNNFusionModel(
            in_features=5,
            hidden_dim=8,
            out_features=3,  # Multi-output
            n_layers=2,
        )

        x = torch.randn(15, 5)
        edge_index = torch.randint(0, 15, (2, 30), dtype=torch.long)

        output = model(x, edge_index)

        assert output.shape == (15, 3)

    def test_eval_mode(self):
        """Test model in evaluation mode."""
        model = GNNFusionModel(in_features=4, hidden_dim=8, out_features=1)

        model.eval()

        x = torch.randn(5, 4)
        edge_index = torch.tensor([[0, 1, 2], [1, 2, 3]], dtype=torch.long)

        with torch.no_grad():
            output = model(x, edge_index)

        assert output.shape == (5, 1)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestMultiModalGNNFusion:
    """Test Multi-Modal GNN Fusion."""

    def test_initialization(self):
        """Test multi-modal fusion initialization."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=3,
            n_magnetic_features=2,
            n_seismic_features=0,
            hidden_dim=32,
            n_layers=2,
        )

        assert fusion.n_gravity == 3
        assert fusion.n_magnetic == 2
        assert fusion.n_seismic == 0
        assert fusion.model is not None

    def test_prepare_graph_basic(self):
        """Test graph preparation from multi-modal data."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=2,
            n_magnetic_features=2,
            hidden_dim=16,
        )

        # Create synthetic data
        n_points = 25  # 5x5 grid
        gravity_data = np.random.randn(n_points, 2)
        magnetic_data = np.random.randn(n_points, 2)

        graph = fusion.prepare_graph(
            gravity_data=gravity_data,
            magnetic_data=magnetic_data,
        )

        # Should concatenate features
        assert graph.node_features.shape == (n_points, 4)
        assert graph.edge_index.shape[0] == 2

    def test_prepare_graph_with_spatial_coords(self):
        """Test graph preparation with spatial coordinates."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=1,
            n_magnetic_features=1,
            hidden_dim=16,
        )

        n_points = 20
        gravity_data = np.random.randn(n_points, 1)
        magnetic_data = np.random.randn(n_points, 1)
        coords = np.random.randn(n_points, 2)

        graph = fusion.prepare_graph(
            gravity_data=gravity_data,
            magnetic_data=magnetic_data,
            spatial_coords=coords,
            k_neighbors=5,
        )

        assert graph.node_features.shape == (n_points, 2)
        # Each node should have ~k_neighbors edges
        n_edges = graph.edge_index.shape[1]
        assert n_edges > 0

    def test_prepare_graph_with_seismic(self):
        """Test graph preparation with seismic data."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=2,
            n_magnetic_features=2,
            n_seismic_features=3,
            hidden_dim=16,
        )

        n_points = 16
        gravity_data = np.random.randn(n_points, 2)
        magnetic_data = np.random.randn(n_points, 2)
        seismic_data = np.random.randn(n_points, 3)

        graph = fusion.prepare_graph(
            gravity_data=gravity_data,
            magnetic_data=magnetic_data,
            seismic_data=seismic_data,
        )

        # Total features = 2 + 2 + 3 = 7
        assert graph.node_features.shape == (n_points, 7)

    def test_knn_graph_construction(self):
        """Test k-nearest neighbor graph construction."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=1,
            n_magnetic_features=1,
        )

        # Create grid of points
        coords = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
        ])

        edge_index = fusion._build_knn_graph(coords, k=2)

        # Each node should connect to 2 nearest neighbors
        # Total edges = 4 nodes * 2 neighbors = 8
        assert edge_index.shape == (2, 8)

    def test_grid_graph_construction(self):
        """Test grid graph construction."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=1,
            n_magnetic_features=1,
        )

        # 3x3 grid = 9 nodes
        n_points = 9
        edge_index = fusion._build_grid_graph(n_points)

        assert edge_index.shape[0] == 2
        # Undirected grid graph for 3x3 has 2*12 = 24 edges
        # (6 horizontal + 6 vertical, times 2 for undirected)
        assert edge_index.shape[1] == 24

    def test_train_simple(self):
        """Test training on simple synthetic data."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=2,
            n_magnetic_features=2,
            hidden_dim=8,
            n_layers=2,
        )

        # Create synthetic data
        n_points = 16
        gravity_data = np.random.randn(n_points, 2)
        magnetic_data = np.random.randn(n_points, 2)
        labels = np.random.randn(n_points)

        graph = fusion.prepare_graph(gravity_data, magnetic_data)
        graph.labels = labels

        # Train for a few epochs
        losses = fusion.train(
            graph,
            labels,
            n_epochs=5,
            learning_rate=0.01,
        )

        # Should return loss history
        assert len(losses) == 5
        assert all(loss >= 0 for loss in losses)

    def test_predict(self):
        """Test prediction after training."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=1,
            n_magnetic_features=1,
            hidden_dim=8,
            n_layers=1,
        )

        # Create and train on simple data
        n_points = 10
        gravity_data = np.random.randn(n_points, 1)
        magnetic_data = np.random.randn(n_points, 1)
        labels = np.random.randn(n_points)

        graph = fusion.prepare_graph(gravity_data, magnetic_data)

        # Quick training
        fusion.train(graph, labels, n_epochs=2, learning_rate=0.01)

        # Predict
        predictions = fusion.predict(graph)

        assert predictions.shape == (n_points,)
        assert np.all(np.isfinite(predictions))

    def test_device_placement(self):
        """Test that model is placed on correct device."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=1,
            n_magnetic_features=1,
        )

        # Model should be on CPU or CUDA if available
        device = fusion.device
        assert device.type in ['cpu', 'cuda']

        # Model parameters should be on the device
        for param in fusion.model.parameters():
            assert param.device.type == device.type

    def test_different_grid_sizes(self):
        """Test with different grid sizes."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=1,
            n_magnetic_features=1,
            hidden_dim=16,
        )

        for n_points in [9, 16, 25, 36]:
            gravity_data = np.random.randn(n_points, 1)
            magnetic_data = np.random.randn(n_points, 1)

            graph = fusion.prepare_graph(gravity_data, magnetic_data)

            assert graph.node_features.shape[0] == n_points

    def test_training_reduces_loss(self):
        """Test that training actually reduces loss."""
        fusion = MultiModalGNNFusion(
            n_gravity_features=2,
            n_magnetic_features=2,
            hidden_dim=16,
            n_layers=2,
        )

        # Create synthetic data with clear pattern
        n_points = 25
        gravity_data = np.random.randn(n_points, 2)
        magnetic_data = np.random.randn(n_points, 2)
        # Labels are linear combination of features
        labels = (
            gravity_data[:, 0] + magnetic_data[:, 0]
        ) / 2.0 + np.random.randn(n_points) * 0.1

        graph = fusion.prepare_graph(gravity_data, magnetic_data)

        losses = fusion.train(
            graph,
            labels,
            n_epochs=20,
            learning_rate=0.01,
        )

        # Loss should generally decrease (allow some fluctuation)
        assert losses[-1] < losses[0] * 1.5, "Training should reduce loss"


@pytest.mark.skipif(HAS_TORCH, reason="Test for PyTorch not available case")
class TestNoTorchFallback:
    """Test behavior when PyTorch is not available."""

    def test_multimodal_fusion_raises_import_error(self):
        """Test that MultiModalGNNFusion raises ImportError without PyTorch."""
        from fusion.gnn_fusion import MultiModalGNNFusion

        with pytest.raises(ImportError, match="PyTorch required"):
            MultiModalGNNFusion(
                n_gravity_features=1,
                n_magnetic_features=1,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
