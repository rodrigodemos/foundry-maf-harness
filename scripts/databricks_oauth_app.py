"""Register a Databricks-native custom OAuth (U2M) app for identity passthrough.

Why Databricks-native OIDC (not the AzureDatabricks first-party app): Foundry blocks passing a
Microsoft-audience token to a third-party MCP endpoint ("Cannot pass Microsoft token to untrusted
MCP endpoint"). A Databricks custom OAuth app has an audience you control, while users still
authenticate with their Entra identity (the workspace uses Entra as IdP), so Unity Catalog still
evaluates the real user.

Requires: Databricks ACCOUNT ADMIN. Needs your Databricks account id.
Run:
    az login
    uv sync --extra scripts
    uv run python scripts/databricks_oauth_app.py \
        --account-id <databricks-account-id> \
        --redirect-url "<FOUNDRY_REDIRECT_URL>"   # add the Foundry-provided redirect after the connection exists

On first run you won't yet have the Foundry redirect URL. Create the app with a placeholder,
create the Foundry connection, then re-run with --redirect-url to update it.
"""

from __future__ import annotations

import argparse
import sys

# Databricks OIDC endpoints for reference (workspace-scoped U2M):
#   authorize: https://<workspace-host>/oidc/v1/authorize
#   token:     https://<workspace-host>/oidc/v1/token
# Scopes: "all-apis offline_access"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account-id", required=True, help="Databricks account id")
    ap.add_argument("--account-host", default="https://accounts.azuredatabricks.net")
    ap.add_argument("--name", default="maf-orchestrator-passthrough")
    ap.add_argument("--redirect-url", action="append", default=[], help="Repeatable")
    ap.add_argument("--confidential", action="store_true", help="Issue a client secret")
    args = ap.parse_args()

    try:
        from databricks.sdk import AccountClient
    except ImportError:
        sys.exit("databricks-sdk not installed. Run: uv sync --extra scripts")

    a = AccountClient(host=args.account_host, account_id=args.account_id)

    redirects = args.redirect_url or ["https://localhost/placeholder-replace-after-phase-4"]
    print(f"[oauth_app] Creating custom OAuth app '{args.name}' with redirects={redirects}")

    created = a.custom_app_integration.create(
        name=args.name,
        redirect_urls=redirects,
        scopes=["all-apis", "offline_access"],
        confidential=args.confidential,
    )

    print("\n[oauth_app] Created. Save these for the Foundry connection:")
    print(f"  client_id     : {created.client_id}")
    if getattr(created, "client_secret", None):
        print(f"  client_secret : {created.client_secret}  (shown once - store securely)")
    print("  auth_url      : https://<workspace-host>/oidc/v1/authorize")
    print("  token_url     : https://<workspace-host>/oidc/v1/token")
    print("  scopes        : all-apis offline_access")


if __name__ == "__main__":
    main()
