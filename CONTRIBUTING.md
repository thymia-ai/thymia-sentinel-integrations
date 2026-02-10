# Contributing to Thymia Sentinel

Thank you for your interest in contributing to Thymia Sentinel!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/thymia-ai/thymia-sentinel-integrations.git
cd thymia-sentinel-integrations

# Install all dev dependencies (includes docs tooling + thymia-sentinel in editable mode)
uv sync
```

## Running Examples

Each example has its own dependencies:

```bash
cd examples/livekit  # or pipecat, vapi_api, gemini_live
cp .env.example .env.local
# Add your API keys to .env.local
uv sync
uv run python src/agent.py
```

## Documentation

### Local Preview

```bash
uv run mkdocs serve
# Open http://127.0.0.1:8000
```

### Versioned Documentation

We use [mike](https://github.com/jimporter/mike) for versioned documentation. Docs are automatically deployed when a release is published.

**Preview with version selector:**

```bash
uv run mike deploy 0.1.0 latest  # no --push = local only
uv run mike serve
# Open http://127.0.0.1:8000
```

**Manual deployment** (maintainers only):

```bash
# Deploy a specific version as latest
uv run mike deploy --push --update-aliases 0.2.0 latest

# Deploy a version without setting it as latest (e.g., patch for old version)
uv run mike deploy --push 0.1.1

# Set the default version
uv run mike set-default --push latest
```

## Release Process

1. **Update version** in `packages/thymia-sentinel/pyproject.toml`

2. **Update CHANGELOG** (if you have one)

3. **Create a release on GitHub**:
   - Tag format: `v0.2.0`
   - This triggers automatic:
     - PyPI package publish (if configured)
     - Documentation deployment

4. **Verify deployment**:
   - Check https://thymia-ai.github.io/thymia-sentinel-integrations/
   - Verify version selector shows new version

## Adding a New Integration

1. Create a new directory under `examples/`:
   ```
   examples/your-framework/
   ├── src/
   │   ├── agent.py
   │   └── prompts.py
   ├── .env.example
   ├── pyproject.toml
   └── README.md
   ```

2. Add documentation in `docs/integrations/your-framework.md`

3. Add to `mkdocs.yml` nav section

4. Update the main `README.md` integrations table

## Code Style

- Use Python 3.10+ features
- Type hints for public APIs
- Docstrings in Google style
- Format with `black` (default settings)

## Questions?

Open an issue or reach out to support@thymia.ai
