"""Container/code-deploy entry point: serve the harness agent over the Foundry Responses protocol.

We use the framework-agnostic `azure-ai-agentserver-responses` host and register a handler that runs
the MAF *harness* agent inside an AgentSession (which the harness's tool-approval/todo/memory
providers require). The higher-level `agent-framework-foundry-hosting` ResponsesHostServer targets
plain agents and does not create a session, so it is not used here.

The host serves /responses and /readiness on port 8088 - the port the Foundry Hosted Agent platform
routes to. The agent is built lazily on first request so /readiness succeeds even before the model
credential / project endpoint is reachable.

Local test:
    uv run maf-orchestrator
    curl -s http://localhost:8088/responses -H "Content-Type: application/json" \\
         -d '{"input": "Where is Seattle?", "stream": false}'
"""

from __future__ import annotations

import inspect
import logging
import re

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    TextResponse,
)

from .agent import build_agent
from .settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("maf_orchestrator")

host = ResponsesAgentServerHost()


async def _resolve(value):
    """Await value if it is awaitable, else return it."""
    if inspect.isawaitable(value):
        return await value
    return value


@host.response_handler
def handle(request: CreateResponse, context: ResponseContext, cancellation_signal=None):
    """Handle one /responses call by running the harness agent on the user's input.

    The host calls this synchronously and consumes the returned TextResponse; async work happens in
    `produce_text`, which the host awaits. We build the agent PER REQUEST so its tools reflect the
    current caller's Databricks consent state (see agent.build_agent / tools.build_tools_with_consent):
    consented callers get the Genie tool; others get a normal chat agent that only offers a consent
    link on data questions. The harness requires an AgentSession, created per request.
    """

    async def produce_text(*_args, **_kwargs) -> str:
        agent = await build_agent(get_settings())

        conv = getattr(request, "conversation", None)
        session_id = conv if isinstance(conv, str) else None
        session = (
            agent.create_session(session_id=session_id) if session_id else agent.create_session()
        )

        # Give the agent the full conversation (prior turns + current input) so multi-turn context
        # works. Reuse the Foundry hosting converters; fall back to latest text if unavailable.
        try:
            from agent_framework_foundry_hosting._responses import (  # type: ignore
                _items_to_messages,
                _output_items_to_messages,
            )

            input_items = await context.get_input_items()
            history = await context.get_history()
            messages = [
                *(await _output_items_to_messages(history)),
                *(await _items_to_messages(input_items)),
            ]
            run_input: object = messages
        except Exception as exc:  # noqa: BLE001
            logger.warning("History conversion unavailable (%s); using latest message only.", exc)
            run_input = await _resolve(context.get_input_text())

        try:
            run_result = await _resolve(agent.run(run_input, session=session))
            return getattr(run_result, "text", None) or str(run_result)
        except Exception as exc:  # noqa: BLE001
            # Safety net: if a tool still surfaces an OAuth consent requirement, show the link
            # rather than a 500.
            msg = str(exc)
            m = re.search(r"https://[^\s\"'\\)]+consent[^\s\"'\\)]+", msg)
            if m:
                logger.info("Surfacing Databricks consent link to user.")
                return (
                    "To access your Databricks I need your approval. Please sign in and approve "
                    "here, then ask again:\n\n" + m.group(0)
                )
            logger.exception("Agent run failed")
            raise

    return TextResponse(context, request, text=produce_text)


def main() -> None:
    settings = get_settings()
    if not settings.project_endpoint:
        logger.warning(
            "FOUNDRY_PROJECT_ENDPOINT is not set. In the hosted sandbox it is injected "
            "automatically; for local dev, set it in .env."
        )
    logger.info("Serving harness agent on http://0.0.0.0:8088 (Responses protocol)")
    host.run(port=8088)


if __name__ == "__main__":
    main()
