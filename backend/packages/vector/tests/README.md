# VolcEngine Embedding Tests

This directory contains tests for the VolcEngine embedding provider.

## Running Tests

### All Tests
To run all VolcEngine tests (mostly mocked):
```bash
cd backend
uv run pytest packages/vector/tests/test_volc_engine.py -v
```

### Manual Integration Test
To run the manual integration test with real VolcEngine API:

1. Set your VolcEngine API key as an environment variable:
   ```bash
   export ARK_API_KEY=your-volcengine-api-key-here
   ```

2. Optionally set custom model and dimension:
   ```bash
   export VOLCENGINE_MODEL=doubao-embedding
   export VOLCENGINE_DIMENSION=1024
   ```

3. Run the manual integration test:
   ```bash
   cd backend
   uv run pytest packages/vector/tests/test_volc_engine.py::test_volcengine_manual_integration -v -s
   ```

### Real API Test
Alternatively, you can run the original real API test:
```bash
cd backend
uv run pytest packages/vector/tests/test_volc_engine.py::test_real_api_call -v -s
```

## Test Differences

- **Mocked Tests**: Most tests use mocked responses and don't require API keys
- **test_real_api_call**: Basic integration test with real API
- **test_volcengine_manual_integration**: Comprehensive manual test with multiple languages and similarity checks

## CI Behavior

In CI environments, all tests requiring real API keys are automatically skipped.
