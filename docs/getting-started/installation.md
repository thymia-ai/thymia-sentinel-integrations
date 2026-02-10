# Installation

## Requirements

- Python 3.9 or higher
- A Python package manager (pip, uv, or similar)
- A Thymia API key ([contact us](mailto:support@thymia.ai) for access)

## Install from PyPI

```bash
pip install thymia-sentinel
```

Or with uv:

```bash
uv add thymia-sentinel
```

## Configuration

Set your API key as an environment variable:

```bash
export THYMIA_API_KEY="your-api-key-here"
```

Or pass it directly to the client:

```python
from thymia_sentinel import SentinelClient

sentinel = SentinelClient(
    api_key="your-api-key-here",
    # ... other config
)
```

## Framework-Specific Installation

For framework integrations, install the example dependencies:

=== "LiveKit"

    ```bash
    cd examples/livekit
    uv sync
    ```

=== "Pipecat"

    ```bash
    cd examples/pipecat
    uv sync
    ```

=== "VAPI"

    ```bash
    cd examples/vapi_api
    uv sync
    ```

=== "Gemini Live"

    ```bash
    cd examples/gemini_live
    uv sync
    ```

## Verify Installation

```python
from thymia_sentinel import SentinelClient, __version__

print(f"thymia-sentinel version: {__version__}")
```

## Development Installation

To install from source for development:

```bash
git clone https://github.com/thymia-ai/thymia-sentinel-integrations.git
cd thymia-sentinel-integrations

# Install the package in editable mode
pip install -e packages/thymia-sentinel

# Or with uv
cd packages/thymia-sentinel
uv sync
```
