# MAF harness → Foundry Hosted Agent → Databricks Genie (per-user RBAC)

A **Microsoft Agent Framework (MAF) harness** agent, deployed as a **Foundry Hosted Agent**, that
answers business/data questions by querying **Databricks Genie (Unity Catalog)** over **MCP** —
carrying the **signed-in user's identity** end-to-end via **OAuth identity passthrough** so Unity
Catalog enforces that user's row/column/table security (RLS / RBAC).

```
User (Entra) ─► Teams / Playground ─► Foundry Agent Service ─► Hosted Agent (this container)
   └─► MAF harness (Responses protocol)
        └─► Databricks Genie managed MCP (OAuth identity passthrough)
             └─► Unity Catalog table (per-user RLS / RBAC)
```

Because the calling user's identity is forwarded all the way to Databricks, two people asking the
*same* question can get *different* answers — each one sees only the rows Unity Catalog grants them.

> This is a **sample**. It contains no secrets or tenant-specific values. Every environment-specific
> value (endpoints, IDs, user names) is supplied at run time through `azd` environment values or a
> local, git-ignored `.env` file. See [Configuration](#configuration).

## Features

- **MAF harness agent** (`create_harness_agent`) — batteries-included agent runtime (function
  invocation, history, compaction, OpenTelemetry) wrapping a `FoundryChatClient`.
- **Foundry Hosted Agent** — deployed with the Azure Developer CLI (`azd`) and the Foundry agent
  extension; serves the **Responses** protocol on port `8088`.
- **Per-user data access** — the Databricks Genie tool is wired through a **Foundry Toolbox** + a
  project **MCP connection** that uses **OAuth identity passthrough**, so Unity Catalog enforces the
  *calling user's* grants (not a shared service account).
- **Graceful consent handling** — before a user consents, the agent stays a normal chat agent and
  only surfaces a consent link when the user actually asks a data question.

## Repository layout

```
src/maf_orchestrator/   # agent code (settings, instructions, tools, agent, server)
deploy/databricks/      # Bicep (project MCP connection + optional agent-identity RBAC)
scripts/                # Databricks data setup, OAuth app registration, Genie guide, smoke test
toolbox.yaml            # Foundry Toolbox definition (Databricks Genie tool)
azure.yaml              # azd config (host: azure.ai.agent, protocol: responses)
Dockerfile              # linux/amd64 image, serves Responses on :8088
main.py                 # code-deploy entry point
.env.sample             # template for local dev — copy to .env (git-ignored) and fill in
```

## Prerequisites

- An existing **Azure AI Foundry** project with a deployed chat model.
- An **Azure Databricks** workspace with **Unity Catalog** and permission to create a serverless SQL
  warehouse, a table, and grants (workspace + metastore admin for the setup script).
- Tooling: `az` CLI, [`azd`](https://learn.microsoft.com/azure/developer/azure-developer-cli/),
  Python 3.13, [`uv`](https://docs.astral.sh/uv/), Docker (optional — `azd` can build in ACR).
- The Foundry agent extension: `azd extension add azure.ai.agents`
- `az login` against the subscription that holds your Foundry project.

## Configuration

All environment-specific values come from **azd environment values** (for deploy) and a local
**`.env`** (for local dev). Nothing sensitive is committed.

Copy the template and fill in your own values:

```bash
cp .env.sample .env      # .env is git-ignored
```

| Variable | Where it's used | Example / notes |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | local dev | `https://<account>.services.ai.azure.com/api/projects/<project>` (injected automatically in the hosted container) |
| `MODEL_DEPLOYMENT_NAME` / `FOUNDRY_MODEL` | agent | your Foundry chat model deployment name, e.g. `gpt-4o` |
| `DATABRICKS_WORKSPACE_URL` | agent / scripts | `https://<workspace-host>.azuredatabricks.net` |
| `DATABRICKS_GENIE_SPACE_ID` | agent | set after the Genie space is created (see below) |
| `DATABRICKS_MCP_CONNECTION_NAME` | agent | name of the Foundry project connection fronting Genie |
| `TOOLBOX_ENDPOINT` | agent | versioned MCP endpoint printed by `azd ai toolbox create` |
| `UC_CATALOG` / `UC_SCHEMA` | agent / scripts | Unity Catalog target, e.g. `<your_catalog>` / `default` |
| `DATABRICKS_WAREHOUSE_ID` | scripts | serverless SQL warehouse id created by the setup script |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | agent | telemetry (injected automatically in the hosted container) |

> **Hosted container:** `FOUNDRY_PROJECT_ENDPOINT` and `APPLICATIONINSIGHTS_CONNECTION_STRING` are
> injected by the platform — do **not** set them for production.

## Local development

```bash
uv sync --extra dev
cp .env.sample .env         # then fill in FOUNDRY_PROJECT_ENDPOINT etc.
uv run maf-orchestrator     # serves http://localhost:8088
curl -s http://localhost:8088/responses -H "Content-Type: application/json" \
     -d '{"input":"Where is Seattle?","stream":false}'
uv run pytest               # light tests (no cloud dependencies)
```

## Deployment (phased)

Some steps require a human decision or admin consent; those are called out as **[manual]**.

### 1. Databricks data + Genie space

Provision a serverless SQL warehouse, a sample Unity Catalog table, and per-user grants:

```bash
uv sync --extra scripts
uv run python scripts/databricks_setup.py \
  --workspace-url https://<workspace-host>.azuredatabricks.net \
  --workspace-resource-id /subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Databricks/workspaces/<workspace> \
  --catalog <your_catalog> --schema default \
  --admin-user <admin-user@example.com> \
  --limited-user <limited-user@example.com>
```

Then create the Genie space over the sample table — see
[`scripts/genie_space_setup.md`](scripts/genie_space_setup.md) **[manual]** — and record the id:

```bash
azd env set DATABRICKS_GENIE_SPACE_ID <SPACE_ID>
```

### 2. Custom OAuth app for identity passthrough **[manual: admin consent]**

```bash
uv run python scripts/databricks_oauth_app.py --account-id <databricks-account-id>
# Entra fallback: scripts/create_entra_app.ps1
```

### 3. Foundry Toolbox

```bash
azd ai toolbox create maf-tools --from-file ./toolbox.yaml \
  --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project>
azd env set TOOLBOX_ENDPOINT <versioned-mcp-endpoint-printed-above>
```

### 4. Deploy the agent

```bash
azd env new <your-azd-env>
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME <your-model-deployment>
azd env set DATABRICKS_WORKSPACE_URL https://<workspace-host>.azuredatabricks.net
azd env set UC_CATALOG <your_catalog>
azd env set UC_SCHEMA default
azd up            # builds in ACR, creates the agent version + a dedicated Entra agent identity
```

### 5. Foundry MCP connection (OAuth identity passthrough)

Create the project connection that fronts the Databricks Genie managed MCP server — via the
`deploy/databricks` Bicep params or the Foundry portal — then add the Foundry-provided redirect URL
back to the OAuth app.

### 6. Smoke test **(handles the consent link)**

```bash
uv run python scripts/smoke_test.py \
  --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project> \
  --agent-name maf-orchestrator --prompt "Total sales by region?"
```

### 7. Publish to Teams

Publishing creates a distinct agent identity; **re-assign** any grants to the new `agentIdentityId`.

## Proving per-user RBAC

The setup script creates one table with a **Unity Catalog row filter** so that an **admin user**
sees all rows and a **limited user** sees only a subset (e.g. one region). Because the agent forwards
each caller's identity to Genie, the same question returns different results per user.

**Test through the front door** (Foundry **playground** or **Teams**), signed in as each user, and
ask *"What were total sales by region?"*:

- **Admin user** → all rows (all regions).
- **Limited user** → only the rows the row filter permits (e.g. one region).

The Databricks query audit attributes each query to the **actual end user**.

> **Important — don't test per-user passthrough via `azd ai agent invoke` or a raw `ai.azure.com`
> token.** Those tokens aren't scoped for the platform's on-behalf-of exchange and fail with
> *"Audience for incoming token is incorrect."* Only the authenticated **playground / Teams** front
> door carries the right user token for OBO.

If the playground also fails OBO, grant the agent's Entra app the **AzureDatabricks
`user_impersonation`** delegated permission and **admin consent**, then retry.

## Notes / known integration points

- `azure.yaml` uses code deploy with `infra.provider: microsoft.foundry`.
- Hosting: framework-agnostic `azure-ai-agentserver-responses` handler that creates an
  `AgentSession` per request (the harness requires one).
- Dependencies pin the granular `agent-framework-*` sub-packages (not the meta package, which pulls
  `azure-functions` — no Python 3.13 wheel).
- Read-only sandbox: the harness file store is rooted at `$HOME`, the only writable path in the
  hosted sandbox.
- Per-user tool: `FoundryToolbox` → toolbox `maf-tools` → Databricks Genie MCP connection with OAuth
  identity passthrough.
- Final per-user validation requires the playground / Teams front door with a human signed in as
  each user (see above).
