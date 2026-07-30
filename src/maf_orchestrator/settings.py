"""Environment-driven configuration.

In the Foundry-hosted container the platform injects several variables automatically
(see https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent):

    FOUNDRY_PROJECT_ENDPOINT          - project endpoint URL
    FOUNDRY_AGENT_NAME / _VERSION     - running agent identity
    FOUNDRY_AGENT_SESSION_ID          - per-request session id
    APPLICATIONINSIGHTS_CONNECTION_STRING - telemetry (OpenTelemetry auto-wired)

Variables we declare ourselves (in azure.yaml `env:` for the azure.ai.agent service) include
MODEL_DEPLOYMENT_NAME and the DATABRICKS_* values below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:  # dotenv is a convenience for local dev only; absent/no-op in the container.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration."""

    project_endpoint: str | None
    model_deployment: str
    databricks_workspace_url: str | None
    genie_space_id: str | None
    mcp_connection_name: str
    toolbox_endpoint: str | None
    uc_catalog: str
    uc_schema: str
    app_insights_connection_string: str | None = field(default=None, repr=False)

    @property
    def genie_mcp_url(self) -> str | None:
        """Databricks Genie *managed MCP* endpoint for the configured space.

        Pattern per Databricks managed-MCP docs:
            https://<workspace-host>/api/2.0/mcp/genie/<space-id>
        """
        if not (self.databricks_workspace_url and self.genie_space_id):
            return None
        base = self.databricks_workspace_url.rstrip("/")
        return f"{base}/api/2.0/mcp/genie/{self.genie_space_id}"

    @property
    def is_hosted(self) -> bool:
        """True when running inside the Foundry Hosted Agent sandbox."""
        return bool(os.environ.get("FOUNDRY_AGENT_NAME"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    model = _first_env("MODEL_DEPLOYMENT_NAME", "FOUNDRY_MODEL", default="gpt-4o") or "gpt-4o"

    # FoundryChatClient reads FOUNDRY_MODEL from the environment; keep both names in sync so the
    # documented env-based path works regardless of which one was set upstream.
    os.environ.setdefault("FOUNDRY_MODEL", model)

    return Settings(
        project_endpoint=_first_env("FOUNDRY_PROJECT_ENDPOINT"),
        model_deployment=model,
        databricks_workspace_url=_first_env("DATABRICKS_WORKSPACE_URL"),
        genie_space_id=_first_env("DATABRICKS_GENIE_SPACE_ID"),
        mcp_connection_name=_first_env(
            "DATABRICKS_MCP_CONNECTION_NAME", default="databricks-genie-mcp"
        )
        or "databricks-genie-mcp",
        toolbox_endpoint=_first_env("TOOLBOX_ENDPOINT"),
        uc_catalog=_first_env("UC_CATALOG", default="main") or "main",
        uc_schema=_first_env("UC_SCHEMA", default="default") or "default",
        app_insights_connection_string=_first_env("APPLICATIONINSIGHTS_CONNECTION_STRING"),
    )
