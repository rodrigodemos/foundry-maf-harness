"""Builds the Microsoft Agent Framework *harness* agent.

The harness (create_harness_agent) wraps a chat client with the full agentic pipeline: function
invocation, planning (todo + plan/execute), per-call history persistence, compaction, approvals,
web search, and OpenTelemetry - all on by default. We only supply the model client, instructions,
and tools. See: https://devblogs.microsoft.com/agent-framework/the-microsoft-agent-framework-harness-is-now-released/
"""

from __future__ import annotations

import logging
import os
import tempfile

from .instructions import INSTRUCTIONS
from .settings import Settings, get_settings
from .tools import build_tools_with_consent

logger = logging.getLogger(__name__)


def _writable_file_store():
    """A harness file store rooted at a WRITABLE directory.

    The Foundry Hosted Agent sandbox mounts the app directory read-only; only $HOME (and /files)
    are writable/persistent. The harness's file-memory/file-access providers otherwise default to a
    path under the read-only app dir, which crashes with 'Read-only file system'. Root them at
    $HOME (persistent across turns in the sandbox) or a temp dir locally.
    """
    from agent_framework import FileSystemAgentFileStore  # type: ignore

    base = os.environ.get("HOME") or os.environ.get("USERPROFILE") or tempfile.gettempdir()
    root = os.path.join(base, "maf-agent-workspace")
    os.makedirs(root, exist_ok=True)
    return FileSystemAgentFileStore(root_directory=root)


def build_chat_client(settings: Settings, credential):
    """Create a FoundryChatClient bound to the project's model deployment.

    Uses the shared DefaultAzureCredential, which resolves to the agent's managed identity in the
    hosted sandbox and to the developer's Azure CLI login locally.
    """
    from agent_framework.foundry import FoundryChatClient  # type: ignore

    # project_endpoint may be None locally (FoundryChatClient falls back to FOUNDRY_PROJECT_ENDPOINT
    # from the environment). In the hosted sandbox it is injected by the platform.
    return FoundryChatClient(
        project_endpoint=settings.project_endpoint,
        model=settings.model_deployment,
        credential=credential,
    )


async def build_agent(settings: Settings | None = None):
    """Construct and return the harness agent (a MAF AIAgent).

    Async because it pre-flights the Foundry Toolbox for the current caller (see tools.py): the Genie
    tool is attached only when the caller has already consented; otherwise a consent link is injected
    into the instructions so the agent asks for consent ONLY on a data question (so "hello" stays a
    normal greeting).
    """
    settings = settings or get_settings()
    from agent_framework import InMemoryHistoryProvider, create_harness_agent  # type: ignore
    from azure.identity import DefaultAzureCredential

    # One credential shared by the model client and the Foundry Toolbox (per-user pass-through).
    credential = DefaultAzureCredential()
    client = build_chat_client(settings, credential)
    tools, consent_link = await build_tools_with_consent(settings, credential)
    file_store = _writable_file_store()

    instructions = INSTRUCTIONS
    if consent_link:
        instructions = (
            INSTRUCTIONS
            + "\n\nDATABRICKS ACCESS: You do NOT currently have access to this user's Databricks "
            "data. For greetings and general questions, answer normally and briefly. ONLY if the "
            "user asks a data/analytics question, reply with exactly this and nothing else:\n"
            f'"To answer that I need to access your Databricks. Please sign in and approve here, '
            f'then ask again: {consent_link}"'
        )
    elif not tools:
        instructions = (
            INSTRUCTIONS
            + "\n\nDATABRICKS ACCESS: The Databricks data tool is temporarily unavailable. Answer "
            "greetings and general questions normally. If the user asks a data question, briefly "
            "say the data source is temporarily unavailable and to try again shortly. Do NOT invent "
            "any figures."
        )

    logger.info(
        "Building harness agent (model=%s, tools=%d, consent_pending=%s, hosted=%s)",
        settings.model_deployment,
        len(tools),
        bool(consent_link),
        settings.is_hosted,
    )

    return create_harness_agent(
        client=client,
        agent_instructions=instructions,
        tools=tools,
        # Conversational data assistant: turn OFF the plan/execute mode and the todo list so the
        # agent answers/queries directly instead of narrating a plan or over-asking for scope.
        disable_mode=True,
        disable_todo=True,
        # The Foundry hosting server (ResponsesHostServer) manages conversation history, so the
        # harness must not also LOAD history (load_messages=False), or hosting rejects startup.
        history_provider=InMemoryHistoryProvider(load_messages=False),
        # Root the harness workspace at a writable dir ($HOME in the sandbox); the app dir is
        # read-only in the Hosted Agent sandbox.
        file_memory_store=file_store,
        file_access_store=file_store,
        # History is managed by the Foundry hosting infrastructure per conversation, so we don't
        # ask the model service to also store it. Avoids duplicate/echoed history.
        default_options={"store": False},
    )
