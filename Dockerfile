# Foundry Hosted Agents require linux/amd64. On Apple Silicon build with:
#   docker build --platform linux/amd64 -t maf-orchestrator:dev .
# (azd builds remotely in ACR by default, so local Docker is optional.)
FROM --platform=linux/amd64 python:3.13-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependency layer (cached): copy only what uv needs to resolve.
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv sync --no-dev

# Hosted agents serve on port 8088 (Responses protocol + /readiness).
EXPOSE 8088

# Entry point: builds the harness agent and serves it via from_agent_framework(agent).run()
CMD ["uv", "run", "--no-dev", "maf-orchestrator"]
