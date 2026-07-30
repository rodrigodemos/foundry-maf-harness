"""End-to-end smoke test against the deployed hosted agent.

Uses the Foundry project's OpenAI-compatible client bound to the agent, and handles the
OAuth identity-passthrough consent handshake (oauth_consent_request -> consent_link -> resubmit
with previous_response_id).

Prereqs:
    az login   (as the user you want to test as, e.g. the admin or the limited user)
    uv sync --extra scripts
Run:
    uv run python scripts/smoke_test.py \
        --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project> \
        --agent-name maf-orchestrator \
        --prompt "What were total sales by region?"
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-endpoint", required=True)
    ap.add_argument("--agent-name", default="maf-orchestrator")
    ap.add_argument("--prompt", default="What were total sales by region?")
    args = ap.parse_args()

    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
    except ImportError:
        sys.exit("Missing deps. Run: uv sync --extra scripts")

    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=args.project_endpoint, credential=credential)
    client = project.get_openai_client(agent_name=args.agent_name)

    print(f"[smoke_test] Asking '{args.agent_name}': {args.prompt}")
    response = client.responses.create(input=args.prompt)

    consent_link = _find_consent_link(response)
    if consent_link:
        print("\n[smoke_test] OAuth consent required (identity passthrough).")
        print("  Open this link, sign in, and approve access, then re-run this script:")
        print(f"  {consent_link}\n")
        # After consent, resubmit referencing the previous response id:
        #   client.responses.create(previous_response_id=response.id, input=args.prompt)
        return

    text = getattr(response, "output_text", None)
    print("\n[smoke_test] Answer:\n" + (text or str(response)))


def _find_consent_link(response) -> str | None:
    """Scan response output items for an oauth_consent_request consent_link."""
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) == "oauth_consent_request":
            link = getattr(item, "consent_link", None)
            if link:
                return link
        # dict-shaped fallback
        if isinstance(item, dict) and item.get("type") == "oauth_consent_request":
            return item.get("consent_link")
    return None


if __name__ == "__main__":
    main()
