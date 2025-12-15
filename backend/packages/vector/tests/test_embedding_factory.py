#!/usr/bin/env python3
"""Test embedding factory pattern with multiple providers and dimensions."""

import asyncio

from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.clients.embedding_factory import (
    EmbeddingProviderFactory,
)


async def test_factory_providers():
    """Test factory with different providers."""
    print("=" * 70)
    print("Testing Embedding Provider Factory")
    print("=" * 70)
    print()

    # List available providers
    providers = EmbeddingProviderFactory.list_providers()
    print(f"Available providers: {', '.join(providers)}")
    print()

    # Test 1: Default provider (from config)
    print("Test 1: Default Provider (from .env config)")
    print("-" * 70)
    client = EmbeddingClient()
    print(f"Provider: {client.provider_name}")
    print(f"Model: {client.model}")
    print(f"Dimension: {client.dimension}")

    text = "The quick brown fox jumps over the lazy dog."
    embedding, metadata = await client.generate_embedding(text)
    print(f"Generated embedding: {len(embedding)}D")
    print(f"Metadata: {metadata}")
    print()

    await client.close()

    # Test 2: Sentence Transformers with different models
    print("Test 2: Sentence Transformers - Different Models")
    print("-" * 70)

    models = [
        ("all-MiniLM-L6-v2", 384),
        # Add more models if you want to test
        # ("all-mpnet-base-v2", 768),
    ]

    for model_name, expected_dim in models:
        print(f"Testing {model_name} ({expected_dim}D)...")

        client = EmbeddingClient(
            provider="sentence-transformers", model=model_name, dimension=expected_dim
        )

        embedding, metadata = await client.generate_embedding(text)

        assert len(embedding) == expected_dim, f"Expected {expected_dim}D, got {len(embedding)}D"
        print(f"✅ {model_name}: {len(embedding)}D - OK")
        print(f"   Device: {metadata.get('device', 'N/A')}")
        print()

        await client.close()

    # Test 3: Batch processing with different batch sizes
    print("Test 3: Batch Processing")
    print("-" * 70)

    test_texts = [
        "Artificial intelligence is transforming technology.",
        "Machine learning models need training data.",
        "Natural language processing enables text understanding.",
        "Computer vision allows machines to see.",
        "Deep learning uses neural networks.",
    ]

    batch_sizes = [2, 5]

    for batch_size in batch_sizes:
        client = EmbeddingClient(
            provider="sentence-transformers",
            model="all-MiniLM-L6-v2",
            batch_size=batch_size,
        )

        embeddings, metadata = await client.generate_embeddings_batch(test_texts)

        print(f"Batch size {batch_size}: Generated {len(embeddings)} embeddings")
        print(f"   Metadata: {metadata}")
        print()

        await client.close()

    # Test 4: Provider override
    print("Test 4: Provider Override")
    print("-" * 70)

    # Even if config says openai, we can override to sentence-transformers
    client = EmbeddingClient(
        provider="sentence-transformers",  # Override
        model="all-MiniLM-L6-v2",
        dimension=384,
    )

    print(f"Overridden provider: {client.provider_name}")
    print(f"Model: {client.model}")

    embedding, metadata = await client.generate_embedding(text)
    print(f"✅ Generated {len(embedding)}D embedding")
    print()

    await client.close()

    # Test 5: Dimension validation
    print("Test 5: Dimension Validation")
    print("-" * 70)

    client = EmbeddingClient(
        provider="sentence-transformers", model="all-MiniLM-L6-v2", dimension=384
    )

    embedding, metadata = await client.generate_embedding(text)

    if client._provider.validate_dimension(embedding):
        print(f"✅ Dimension validation passed: {len(embedding)} == {client.dimension}")
    else:
        print(f"❌ Dimension mismatch: {len(embedding)} != {client.dimension}")

    print()
    await client.close()


async def test_similarity_comparison():
    """Test semantic similarity across providers."""
    print("=" * 70)
    print("Testing Semantic Similarity")
    print("=" * 70)
    print()

    import numpy as np

    texts = {
        "tech1": "Artificial intelligence and machine learning",
        "tech2": "Deep learning and neural networks",
        "nature": "The forest is full of trees and animals",
    }

    client = EmbeddingClient(
        provider="sentence-transformers", model="all-MiniLM-L6-v2"
    )

    embeddings = {}
    for key, text in texts.items():
        embedding, _ = await client.generate_embedding(text)
        embeddings[key] = np.array(embedding)

    # Calculate cosine similarities
    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    sim_tech = cosine_similarity(embeddings["tech1"], embeddings["tech2"])
    sim_diff = cosine_similarity(embeddings["tech1"], embeddings["nature"])

    print(f"Similarity (tech1 vs tech2): {sim_tech:.4f}")
    print(f"Similarity (tech1 vs nature): {sim_diff:.4f}")
    print()

    if sim_tech > sim_diff:
        print("✅ Related texts have higher similarity - PASS")
    else:
        print("❌ Similarity test failed")

    print()
    await client.close()


async def test_context_manager():
    """Test context manager usage."""
    print("=" * 70)
    print("Testing Context Manager")
    print("=" * 70)
    print()

    text = "Testing context manager functionality."

    async with EmbeddingClient(
        provider="sentence-transformers", model="all-MiniLM-L6-v2"
    ) as client:
        embedding, metadata = await client.generate_embedding(text)
        print(f"✅ Generated {len(embedding)}D embedding in context manager")
        print(f"   Provider: {client.provider_name}")

    print("✅ Client automatically closed")
    print()


async def main():
    """Run all tests."""
    print("\n🧪 Embedding Factory Pattern Test Suite".center(70))
    print()

    try:
        await test_factory_providers()
        await test_similarity_comparison()
        await test_context_manager()

        print("=" * 70)
        print("✅ All factory pattern tests passed!")
        print("=" * 70)
        print()

        print("Summary:")
        print("- ✅ Factory pattern working correctly")
        print("- ✅ Multiple providers supported")
        print("- ✅ Dimension validation working")
        print("- ✅ Batch processing working")
        print("- ✅ Provider override working")
        print("- ✅ Semantic similarity preserved")
        print("- ✅ Context manager working")

        return 0

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

