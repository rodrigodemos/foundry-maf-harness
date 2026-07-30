"""Tool wiring for the harness agent - Databricks Genie via Foundry Toolbox (per-user OAuth2).

Why a per-request pre-flight?
  The harness eagerly lists an attached tool's tools on EVERY turn. The Databricks Genie tool uses
  the Foundry OAuth2 consent flow, so before the caller consents, that listing returns
  CONSENT_REQUIRED - which would make even "hello" demand consent. To avoid that, we pre-flight the
  toolbox for THIS caller:
    - consent already granted  -> attach the Genie tool (full data access).
    - consent NOT granted      -> attach nothing, and hand back a consent link so the agent can ask
                                  for consent ONLY when the user poses a data question.

Identity: the toolbox's `databricks-genie` connection is OAuth2 against the Databricks OIDC app, so
after the user consents once, Foundry stores their Databricks token and forwards it per-user -> Unity
Catalog enforces that user's grants (the admin user sees all rows; the limited user only a subset).

Note: UserEntraToken (Entra pass-through) does NOT work for hosted agents today - a known Foundry
platform limitation (GitHub Azure/azure-sdk-for-net#59767) - which is why we use OAuth2 consent.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from .settings import Settings

logger = logging.getLogger(__name__)


def _extract_consent_link(message: str) -> str | None:
    m = re.search(r"https://[^\s\"'\\)]+consent[^\s\"'\\)]+", message)
    return m.group(0) if m else None


async def build_tools_with_consent(settings: Settings, credential: Any) -> tuple[list[Any], str | None]:
    """Return (tools, consent_link).

    Pre-flights the Foundry Toolbox for the current caller and NEVER lets a tool error crash the
    turn:
      - pre-flight succeeds                 -> attach the Genie tool (full data access).
      - pre-flight needs consent            -> no tool + consent link (agent offers it on data Qs).
      - pre-flight fails (permission/transient, retried once) -> no tool + no link (agent stays a
        normal chat agent and says data is temporarily unavailable on data Qs). This avoids the
        harness eagerly re-listing a broken tool and 500-ing even simple "hello" turns.
    """
    if not settings.toolbox_endpoint:
        logger.warning("TOOLBOX_ENDPOINT not set; starting agent with no data tools.")
        return [], None

    try:
        from agent_framework_foundry_hosting import FoundryToolbox  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("FoundryToolbox unavailable (%s); starting tool-less.", exc)
        return [], None

    last_exc: Exception | None = None
    for attempt in range(2):
        probe = FoundryToolbox(credential)
        try:
            async with probe:  # entering the context performs tools/list for THIS caller
                pass
            logger.info("Databricks consent+access OK for caller; attaching Genie tool.")
            return [FoundryToolbox(credential, timeout=180.0)], None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            link = _extract_consent_link(str(exc))
            if link:
                logger.info("Caller has not consented to Databricks; offering consent link.")
                return [], link
            logger.warning("Toolbox pre-flight attempt %d failed (non-consent): %s", attempt + 1, exc)
            await asyncio.sleep(1)

    # Persistent non-consent failure (e.g., missing permissions): degrade to a tool-less agent
    # rather than attaching a tool that would crash the harness on its eager tools/list.
    logger.warning("Toolbox unavailable for caller after retries: %s", last_exc)
    return [], None


__all__ = ["build_tools_with_consent"]
