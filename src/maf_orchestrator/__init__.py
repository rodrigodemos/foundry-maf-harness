"""maf_orchestrator - a Microsoft Agent Framework harness agent for Foundry hosted deployment.

Modules:
    settings  - environment-driven configuration.
    tools     - Databricks Genie (managed MCP) tool wiring with per-user identity passthrough.
    agent     - builds the MAF harness agent.
    server    - container entrypoint that serves the Foundry Responses protocol on :8088.
"""

from .settings import Settings, get_settings

# NOTE: build_agent is intentionally NOT imported here - it pulls in agent_framework, which we keep
# out of the light import path (settings, tests). Import it directly where needed:
#     from maf_orchestrator.agent import build_agent

__all__ = ["Settings", "get_settings"]
