"""Lightweight tests that don't require agent_framework/Azure SDKs to be installed."""

from __future__ import annotations

import os

from maf_orchestrator.settings import Settings


def _settings(**over) -> Settings:
    base = dict(
        project_endpoint="https://x/api/projects/sample",
        model_deployment="gpt-4o",
        databricks_workspace_url="https://adb-1.2.azuredatabricks.net",
        genie_space_id=None,
        mcp_connection_name="databricks-genie-mcp",
        toolbox_endpoint=None,
        uc_catalog="main",
        uc_schema="default",
    )
    base.update(over)
    return Settings(**base)


def test_genie_mcp_url_none_without_space():
    assert _settings(genie_space_id=None).genie_mcp_url is None


def test_genie_mcp_url_built_when_configured():
    s = _settings(genie_space_id="abc123")
    assert s.genie_mcp_url == "https://adb-1.2.azuredatabricks.net/api/2.0/mcp/genie/abc123"


def test_is_hosted_reads_env(monkeypatch):
    monkeypatch.delenv("FOUNDRY_AGENT_NAME", raising=False)
    assert _settings().is_hosted is False
    monkeypatch.setenv("FOUNDRY_AGENT_NAME", "maf-orchestrator")
    assert _settings().is_hosted is True
