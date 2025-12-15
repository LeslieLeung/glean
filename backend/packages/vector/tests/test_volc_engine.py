"""Tests for Volcengine Ark embedding provider using official SDK."""

import os
from unittest.mock import MagicMock, patch

import pytest

from glean_vector.clients.providers import VolcEngineProvider
import numpy as np


@pytest.fixture
def volc_config():
    """Volcengine provider configuration."""
    return {
        "model": "doubao-embedding",
        "dimension": 1024,
        "api_key": "test-api-key",
        "timeout": 30,
        "max_retries": 3,
        "batch_size": 4,
    }


@pytest.fixture
def mock_ark_response_single():
    """Mock Ark response for single embedding."""
    mock_response = MagicMock()
    mock_response.model = "doubao-embedding"

    # Mock data item
    mock_data_item = MagicMock()
    mock_data_item.index = 0
    mock_data_item.embedding = [0.1] * 1024

    mock_response.data = [mock_data_item]

    # Mock usage
    mock_usage = MagicMock()
    mock_usage.total_tokens = 10
    mock_response.usage = mock_usage

    return mock_response


@pytest.fixture
def mock_ark_response_batch():
    """Mock Ark response for batch embeddings."""
    mock_response = MagicMock()
    mock_response.model = "doubao-embedding"

    # Mock data items
    mock_data_items = []
    for i in range(3):
        mock_item = MagicMock()
        mock_item.index = i
        mock_item.embedding = [0.1 * (i + 1)] * 1024
        mock_data_items.append(mock_item)

    mock_response.data = mock_data_items

    # Mock usage
    mock_usage = MagicMock()
    mock_usage.total_tokens = 30
    mock_response.usage = mock_usage

    return mock_response


@pytest.mark.asyncio
async def test_provider_initialization(volc_config):
    """Test provider initialization."""
    provider = VolcEngineProvider(**volc_config)

    assert provider.model == "doubao-embedding"
    assert provider.dimension == 1024
    assert provider.api_key == "test-api-key"
    assert provider.timeout == 30
    assert provider.max_retries == 3
    assert provider.batch_size == 4

    await provider.close()


@pytest.mark.asyncio
async def test_provider_initialization_with_custom_base_url(volc_config):
    """Test provider initialization with custom base URL."""
    volc_config["base_url"] = "https://custom-api.example.com"
    provider = VolcEngineProvider(**volc_config)

    assert provider.base_url == "https://custom-api.example.com"

    await provider.close()


@pytest.mark.asyncio
async def test_generate_embedding_success(volc_config, mock_ark_response_single):
    """Test successful single embedding generation."""
    provider = VolcEngineProvider(**volc_config)

    # Mock the Ark client
    with patch("volcenginesdkarkruntime.Ark") as MockArk:
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_ark_response_single
        MockArk.return_value = mock_client

        embedding, metadata = await provider.generate_embedding("test text")

        assert len(embedding) == 1024
        assert embedding == [0.1] * 1024
        assert metadata["model"] == "doubao-embedding"
        assert metadata["total_tokens"] == 10
        assert metadata["provider"] == "volc_engine"

        # Verify API was called correctly
        mock_client.embeddings.create.assert_called_once_with(
            model="doubao-embedding", input=["test text"]
        )

    await provider.close()


@pytest.mark.asyncio
async def test_generate_embeddings_batch_success(volc_config, mock_ark_response_batch):
    """Test successful batch embedding generation."""
    provider = VolcEngineProvider(**volc_config)

    # Mock the Ark client
    with patch("volcenginesdkarkruntime.Ark") as MockArk:
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_ark_response_batch
        MockArk.return_value = mock_client

        texts = ["text 1", "text 2", "text 3"]
        embeddings, metadata = await provider.generate_embeddings_batch(texts)

        assert len(embeddings) == 3
        assert embeddings[0] == pytest.approx([0.1] * 1024)
        assert embeddings[1] == pytest.approx([0.2] * 1024)
        assert embeddings[2] == pytest.approx([0.3] * 1024)
        assert metadata["model"] == "doubao-embedding"
        assert metadata["total_tokens"] == 30
        assert metadata["count"] == 3

        # Verify API was called correctly
        mock_client.embeddings.create.assert_called_once_with(
            model="doubao-embedding", input=texts
        )

    await provider.close()


@pytest.mark.asyncio
async def test_batch_size_exceeded(volc_config):
    """Test batch size validation."""
    provider = VolcEngineProvider(**volc_config)

    texts = ["text"] * 5  # Exceeds batch_size of 4

    with pytest.raises(ValueError, match="Batch size .* exceeds limit"):
        await provider.generate_embeddings_batch(texts)

    await provider.close()


@pytest.mark.asyncio
async def test_dimension_validation_failure(volc_config):
    """Test dimension validation failure."""
    provider = VolcEngineProvider(**volc_config)

    # Mock response with wrong dimension
    mock_response = MagicMock()
    mock_response.model = "doubao-embedding"

    mock_data_item = MagicMock()
    mock_data_item.embedding = [0.1] * 512  # Wrong dimension
    mock_response.data = [mock_data_item]

    mock_usage = MagicMock()
    mock_usage.total_tokens = 10
    mock_response.usage = mock_usage

    with patch("volcenginesdkarkruntime.Ark") as MockArk:
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response
        MockArk.return_value = mock_client

        with pytest.raises(ValueError, match="Dimension mismatch"):
            await provider.generate_embedding("test text")

    await provider.close()


@pytest.mark.asyncio
async def test_provider_name():
    """Test provider name property."""
    provider = VolcEngineProvider(
        model="doubao-embedding", dimension=1024, api_key="test"
    )

    assert provider.provider_name == "volc_engine"

    await provider.close()


@pytest.mark.asyncio
async def test_import_error_handling(volc_config):
    """Test handling of missing volcenginesdkarkruntime package."""
    provider = VolcEngineProvider(**volc_config)

    with patch("volcenginesdkarkruntime.Ark", side_effect=ImportError("No module")):
        with pytest.raises(ImportError, match="volcenginesdkarkruntime is not installed"):
            await provider.generate_embedding("test text")

    await provider.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ARK_API_KEY"),
    reason="ARK_API_KEY not set in environment",
)
async def test_real_api_call():
    """
    Integration test with real Volcengine Ark API.

    This test is skipped unless ARK_API_KEY is set in environment.
    Run with: ARK_API_KEY=your-key pytest test_volc_engine.py::test_real_api_call -v -s
    """
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("VOLCENGINE_MODEL", "doubao-embedding")
    dimension = int(os.getenv("VOLCENGINE_DIMENSION", "1024"))

    provider = VolcEngineProvider(model=model, dimension=dimension, api_key=api_key)

    try:
        # Test single embedding
        embedding, metadata = await provider.generate_embedding(
            "这是一个测试文本，用于验证火山引擎的向量化服务。"
        )
    except ValueError as exc:
        # Ark returns 404 when the model/endpoint is not enabled for the current key.
        # Skip instead of failing so local runs can point to an accessible model as
        # documented at https://www.volcengine.com/docs/82379/1521766?lang=zh
        if "InvalidEndpointOrModel.NotFound" in str(exc):
            pytest.skip(
                "Volcengine model/endpoint not accessible. "
                "Set VOLCENGINE_MODEL to a permitted endpoint per docs."
            )
        raise

    assert len(embedding) == dimension
    assert metadata["provider"] == "volc_engine"
    assert metadata["total_tokens"] > 0

    print(f"Single embedding generated: dimension={len(embedding)}")
    print(f"Metadata: {metadata}")

    # Test batch embeddings
    texts = ["文本1：测试向量化", "文本2：测试批量处理", "文本3：测试API调用"]
    embeddings, metadata = await provider.generate_embeddings_batch(texts)

    assert len(embeddings) == 3
    assert all(len(emb) == dimension for emb in embeddings)
    assert metadata["count"] == 3

    print(f"Batch embeddings generated: count={len(embeddings)}")
    print(f"Metadata: {metadata}")

    await provider.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("CI") == "true" or not os.getenv("ARK_API_KEY"),
    reason="Test skipped in CI environment or when ARK_API_KEY is not set",
)
async def test_volcengine_manual_integration():
    """
    Manual integration test for Volcengine embedding provider.
    
    This test is explicitly skipped in CI environments and when ARK_API_KEY is not set.
    It's designed for manual testing to verify the integration works with real API.
    
    To run this test manually:
    1. Set ARK_API_KEY environment variable with your Volcengine API key
    2. Optionally set VOLCENGINE_MODEL and VOLCENGINE_DIMENSION
    3. Run: pytest test_volc_engine.py::test_volcengine_manual_integration -v -s
    """
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("VOLCENGINE_MODEL", "doubao-embedding")
    dimension = int(os.getenv("VOLCENGINE_DIMENSION", "1024"))

    # Initialize provider with real API
    provider = VolcEngineProvider(
        model=model,
        dimension=dimension,
        api_key=api_key,
        batch_size=2  # Use smaller batch for testing
    )

    try:
        # Test with English text
        english_text = "This is a test sentence for Volcengine embedding generation."
        try:
            embedding_en, metadata_en = await provider.generate_embedding(english_text)
        except ValueError as exc:
            if "InvalidEndpointOrModel.NotFound" in str(exc):
                pytest.skip(
                    "Volcengine model/endpoint not accessible. "
                    "Set VOLCENGINE_MODEL to a permitted endpoint per docs."
                )
            raise

        assert len(embedding_en) == dimension
        assert metadata_en["provider"] == "volc_engine"
        assert metadata_en["total_tokens"] > 0
        assert metadata_en["model"] == model

        print(f"English embedding: dimension={len(embedding_en)}, tokens={metadata_en['total_tokens']}")

        # Test with Chinese text
        chinese_text = "这是一个用于测试火山引擎向量生成的中文句子。"
        embedding_zh, metadata_zh = await provider.generate_embedding(chinese_text)

        assert len(embedding_zh) == dimension
        assert metadata_zh["provider"] == "volc_engine"
        assert metadata_zh["total_tokens"] > 0

        print(f"Chinese embedding: dimension={len(embedding_zh)}, tokens={metadata_zh['total_tokens']}")

        # Test batch processing with mixed languages
        mixed_texts = [
            "First English sentence",
            "第二个中文句子",
            "Third English sentence"
        ]

        embeddings_batch, metadata_batch = await provider.generate_embeddings_batch(mixed_texts)

        assert len(embeddings_batch) == 3
        assert all(len(emb) == dimension for emb in embeddings_batch)
        assert metadata_batch["count"] == 3
        assert metadata_batch["total_tokens"] > 0

        print(f"Batch embeddings: count={len(embeddings_batch)}, total_tokens={metadata_batch['total_tokens']}")

        # Verify embeddings are different for different texts
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed, skipping similarity test")

        # Calculate cosine similarity between first two embeddings
        emb1, emb2 = np.array(embeddings_batch[0]), np.array(embeddings_batch[1])
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

        # Similarity should be less than 1.0 (different texts)
        assert similarity < 0.99, f"Embeddings are too similar: {similarity}"

        print(f"Cosine similarity between first two embeddings: {similarity:.4f}")

        print("All Volcengine integration tests passed!")

    finally:
        await provider.close()
