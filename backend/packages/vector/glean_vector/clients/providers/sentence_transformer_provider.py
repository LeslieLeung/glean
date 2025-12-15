"""Sentence Transformers embedding provider."""

import asyncio
import threading
from typing import Any

from .base import EmbeddingProvider


# Global lock and cache for model loading to prevent concurrent loading issues
_model_lock = threading.Lock()
_model_cache: dict[str, Any] = {}


class SentenceTransformerProvider(EmbeddingProvider):
    """
    Sentence Transformers embedding provider.

    Supports local transformer models for offline embedding generation.
    Automatically detects and uses the best available device (CUDA > MPS > CPU).
    Uses a global model cache to prevent concurrent loading issues.
    """

    def __init__(self, model: str, dimension: int, **kwargs: Any) -> None:
        """
        Initialize Sentence Transformer provider.

        Args:
            model: Model name (HuggingFace model ID)
            dimension: Embedding dimension
            **kwargs: Model configuration
                - device: Device to run on ('cpu', 'cuda', 'mps', 'auto')
                - normalize_embeddings: Whether to normalize vectors
                - batch_size: Max texts per batch
        """
        super().__init__(model, dimension, **kwargs)

        self.device = kwargs.get("device", None)  # None means auto-detect
        self.normalize = kwargs.get("normalize_embeddings", True)
        self.batch_size = kwargs.get("batch_size", 32)

        self._model: Any | None = None
        self._device_info: dict[str, Any] = {}

    def _detect_available_devices(self) -> dict[str, Any]:
        """
        Detect all available compute devices and their capabilities.

        Returns:
            Dictionary with device availability and info.
        """
        info: dict[str, Any] = {
            "cuda_available": False,
            "cuda_device_count": 0,
            "cuda_device_name": None,
            "mps_available": False,
            "mps_built": False,
            "recommended": "cpu",
        }

        try:
            import torch

            # Check CUDA
            if torch.cuda.is_available():
                info["cuda_available"] = True
                info["cuda_device_count"] = torch.cuda.device_count()
                if info["cuda_device_count"] > 0:
                    info["cuda_device_name"] = torch.cuda.get_device_name(0)
                info["recommended"] = "cuda"

            # Check MPS (Apple Silicon)
            if hasattr(torch.backends, "mps"):
                info["mps_built"] = torch.backends.mps.is_built()
                info["mps_available"] = torch.backends.mps.is_available()
                # Only recommend MPS if CUDA is not available
                if info["mps_available"] and not info["cuda_available"]:
                    info["recommended"] = "mps"

        except ImportError:
            pass

        return info

    def _test_device_compatibility(self, device: str) -> bool:
        """
        Test if a device can actually be used for inference.

        Args:
            device: Device string ('cuda', 'mps', 'cpu')

        Returns:
            True if device works, False otherwise.
        """
        try:
            import torch

            # Create a small test tensor and try operations
            if device == "cuda" and torch.cuda.is_available():
                test_tensor = torch.randn(10, 10, device="cuda")
                _ = test_tensor @ test_tensor.T
                return True
            elif device == "mps":
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    test_tensor = torch.randn(10, 10, device="mps")
                    _ = test_tensor @ test_tensor.T
                    return True
            elif device == "cpu":
                return True

        except Exception as e:
            print(f"Device {device} test failed: {e}")

        return False

    def _load_model_with_fallback(self, target_device: str) -> tuple[Any, str]:
        """
        Load model with automatic fallback on failure.

        Args:
            target_device: Preferred device to load on.

        Returns:
            Tuple of (loaded model, actual device used).
        """
        from sentence_transformers import SentenceTransformer

        # Device fallback order
        devices_to_try = []
        if target_device == "cuda":
            devices_to_try = ["cuda", "cpu"]
        elif target_device == "mps":
            devices_to_try = ["mps", "cpu"]
        else:
            devices_to_try = ["cpu"]

        last_error: Exception | None = None

        for device in devices_to_try:
            try:
                print(f"Attempting to load model on {device}...")

                # Try loading with model_kwargs first (sentence-transformers >= 3.0)
                try:
                    model = SentenceTransformer(
                        self.model,
                        device=device,
                        model_kwargs={"low_cpu_mem_usage": False},
                    )
                except TypeError:
                    # Older versions don't support model_kwargs
                    model = SentenceTransformer(self.model, device=device)

                # Verify no meta tensors
                import torch

                if any(p.is_meta for p in model.parameters()):
                    raise RuntimeError("Model has meta tensors after loading")

                # Test encode to ensure it works
                _ = model.encode("test", convert_to_numpy=True)

                print(f"Successfully loaded model on {device}")
                return model, device

            except Exception as e:
                error_str = str(e).lower()
                if "meta tensor" in error_str or "cannot copy out of meta" in error_str:
                    print(f"Meta tensor error on {device}, trying next device...")
                else:
                    print(f"Error loading on {device}: {e}")
                last_error = e
                continue

        # All devices failed
        raise RuntimeError(
            f"Failed to load model on any device. Last error: {last_error}"
        )

    def _get_model(self) -> Any:
        """Get or create Sentence Transformer model with automatic device selection."""
        global _model_cache

        if self._model is None:
            # Check global cache first (without lock for performance)
            cache_key = self.model
            if cache_key in _model_cache:
                cached = _model_cache[cache_key]
                self._model = cached["model"]
                self.device = cached["device"]
                self._device_info = cached["device_info"]
                self.dimension = cached["dimension"]
                return self._model

            # Use lock for thread-safe model loading
            with _model_lock:
                # Double-check after acquiring lock
                if cache_key in _model_cache:
                    cached = _model_cache[cache_key]
                    self._model = cached["model"]
                    self.device = cached["device"]
                    self._device_info = cached["device_info"]
                    self.dimension = cached["dimension"]
                    return self._model

                # Detect available devices
                self._device_info = self._detect_available_devices()
                print(f"Device detection: {self._device_info}")

                # Determine target device
                if self.device and self.device != "auto":
                    target_device = self.device
                else:
                    target_device = self._device_info["recommended"]

                # Test if target device actually works
                if target_device != "cpu" and not self._test_device_compatibility(target_device):
                    print(f"Device {target_device} failed compatibility test, falling back to CPU")
                    target_device = "cpu"

                # Load model with fallback
                self._model, actual_device = self._load_model_with_fallback(target_device)
                self.device = actual_device

                # Verify and update dimension
                test_embedding = self._model.encode(
                    "test", convert_to_numpy=True, normalize_embeddings=self.normalize
                )
                actual_dim = (
                    len(test_embedding) if test_embedding.ndim == 1 else test_embedding.shape[-1]
                )

                if actual_dim != self.dimension:
                    print(
                        f"Warning: Model {self.model} produces {actual_dim}D embeddings, "
                        f"but expected {self.dimension}D. Updating dimension."
                    )
                    self.dimension = actual_dim

                # Cache the loaded model for reuse
                _model_cache[cache_key] = {
                    "model": self._model,
                    "device": self.device,
                    "device_info": self._device_info,
                    "dimension": self.dimension,
                }

                print(
                    f"Model {self.model} loaded successfully on {self.device} "
                    f"(dimension: {self.dimension})"
                )

        return self._model

    async def generate_embedding(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Generate embedding for a single text."""
        loop = asyncio.get_event_loop()

        def _encode() -> tuple[list[float], dict[str, Any]]:
            model = self._get_model()

            embedding_array = model.encode(
                text, convert_to_numpy=True, normalize_embeddings=self.normalize
            )

            # Convert to list and ensure 1D
            if embedding_array.ndim > 1:
                embedding_array = embedding_array.flatten()

            embedding = embedding_array.tolist()

            metadata = {
                "model": self.model,
                "dimension": len(embedding),
                "provider": self.provider_name,
                "device": str(self.device),
                "device_info": self._device_info,
            }

            return embedding, metadata

        # Run in thread pool to avoid blocking
        return await loop.run_in_executor(None, _encode)

    async def generate_embeddings_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """Generate embeddings for multiple texts."""
        loop = asyncio.get_event_loop()

        def _encode_batch() -> tuple[list[list[float]], dict[str, Any]]:
            model = self._get_model()

            # Encode returns numpy array of shape (n_texts, embedding_dim)
            embeddings_array = model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=self.normalize,
                batch_size=self.batch_size,
            )

            # Convert to list of lists
            embeddings = embeddings_array.tolist()

            metadata = {
                "model": self.model,
                "dimension": len(embeddings[0]) if embeddings else 0,
                "provider": self.provider_name,
                "count": len(texts),
                "device": str(self.device),
                "device_info": self._device_info,
            }

            return embeddings, metadata

        # Run in thread pool to avoid blocking
        return await loop.run_in_executor(None, _encode_batch)

    async def close(self) -> None:
        """Clean up model resources (instance only, keeps global cache)."""
        # Don't clear global cache - model is shared across instances
        # Just clear the instance reference
        self._model = None
        self._device_info = {}

    @classmethod
    def clear_model_cache(cls) -> None:
        """Clear the global model cache. Use with caution in production."""
        global _model_cache
        with _model_lock:
            for cache_key in list(_model_cache.keys()):
                try:
                    import torch

                    cached = _model_cache[cache_key]
                    device = cached.get("device", "cpu")
                    if device == "cuda" and torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
            _model_cache.clear()
        print("Model cache cleared")

    def get_device_info(self) -> dict[str, Any]:
        """
        Get current device information.

        Returns:
            Dictionary with device info.
        """
        if not self._device_info:
            self._device_info = self._detect_available_devices()
        return {
            "current_device": self.device,
            **self._device_info,
        }
