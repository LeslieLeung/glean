#!/usr/bin/env python3
"""Quick test script for embedding generation with Sentence Transformers."""

import asyncio
import time

import pytest

from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.config import embedding_config


def _requires_api_key() -> bool:
    """Check if the current embedding provider requires an API key."""
    # Providers that require API keys
    api_key_providers = {"openai", "volcengine", "azure", "cohere"}
    return embedding_config.provider in api_key_providers and not embedding_config.api_key


@pytest.mark.skipif(
    _requires_api_key(),
    reason=f"Embedding provider '{embedding_config.provider}' requires an API key",
)
async def test_single_embedding():
    """Test single text embedding."""
    print("=" * 60)
    print("Testing Single Embedding Generation")
    print("=" * 60)
    print(f"Provider: {embedding_config.provider}")
    print(f"Model: {embedding_config.model}")
    print(f"Expected Dimension: {embedding_config.dimension}")
    print()

    test_text = "This is a test article about artificial intelligence and machine learning."

    client = EmbeddingClient()

    start_time = time.time()
    embedding, metadata = await client.generate_embedding(test_text)
    elapsed = (time.time() - start_time) * 1000  # Convert to ms

    print(f"✅ Embedding generated in {elapsed:.2f}ms")
    print(f"   Dimension: {len(embedding)}")
    print(f"   Metadata: {metadata}")
    print(f"   First 5 values: {embedding[:5]}")
    print()

    await client.close()

    return elapsed, len(embedding)


@pytest.mark.skipif(
    _requires_api_key(),
    reason=f"Embedding provider '{embedding_config.provider}' requires an API key",
)
async def test_batch_embedding():
    """Test batch embedding generation."""
    print("=" * 60)
    print("Testing Batch Embedding Generation")
    print("=" * 60)

    test_texts = [
        "Python is a programming language.",
        "Machine learning models require training data.",
        "The weather is nice today.",
        "Database systems store and retrieve information.",
        "Web development involves HTML, CSS, and JavaScript.",
    ]

    client = EmbeddingClient()

    start_time = time.time()
    embeddings, metadata = await client.generate_embeddings_batch(test_texts)
    elapsed = (time.time() - start_time) * 1000

    print(f"✅ {len(embeddings)} embeddings generated in {elapsed:.2f}ms")
    print(f"   Average per text: {elapsed / len(embeddings):.2f}ms")
    print(f"   Metadata: {metadata}")
    print()

    # Calculate similarity between first two texts (cosine similarity)
    import numpy as np

    vec1 = np.array(embeddings[0])
    vec2 = np.array(embeddings[1])
    vec3 = np.array(embeddings[2])

    # Cosine similarity
    sim_1_2 = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    sim_1_3 = np.dot(vec1, vec3) / (np.linalg.norm(vec1) * np.linalg.norm(vec3))

    print("Similarity Analysis:")
    print(f"   Text 1 vs Text 2 (related): {sim_1_2:.4f}")
    print(f"   Text 1 vs Text 3 (unrelated): {sim_1_3:.4f}")
    print()

    await client.close()


@pytest.mark.skipif(
    _requires_api_key(),
    reason=f"Embedding provider '{embedding_config.provider}' requires an API key",
)
async def test_multilingual():
    """Test multilingual embedding (if using multilingual model)."""
    print("=" * 60)
    print("Testing Multilingual Support")
    print("=" * 60)

    test_texts = {
        "English": "Hello, how are you?",
        "Chinese": "你好，你好吗？",
        "Japanese": "こんにちは、元気ですか？",
        "French": "Bonjour, comment allez-vous?",
    }

    client = EmbeddingClient()

    for lang, text in test_texts.items():
        embedding, metadata = await client.generate_embedding(text)
        print(f"✅ {lang}: {len(embedding)} dimensions")

    print()
    await client.close()


async def main():
    """Run all tests."""
    print("\n" + "🧪 Embedding Client Test Suite".center(60))
    print()

    try:
        # Test 1: Single embedding
        elapsed, dim = await test_single_embedding()

        # Verify dimension
        if dim != embedding_config.dimension:
            print(f"⚠️  Warning: Expected dimension {embedding_config.dimension}, got {dim}")

        # Verify performance
        if elapsed > 500:
            print(f"⚠️  Warning: Embedding took {elapsed:.2f}ms (target: <500ms)")
        else:
            print(f"✅ Performance OK: {elapsed:.2f}ms < 500ms")

        print()

        # Test 2: Batch embedding
        await test_batch_embedding()

        # Test 3: Multilingual (optional)
        if "multilingual" in embedding_config.model.lower():
            await test_multilingual()

        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
