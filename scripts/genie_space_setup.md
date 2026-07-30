# Create the Genie space (workspace action) [manual, ~2 min]

Everything else is done by `scripts/databricks_setup.py`. Only the Genie space itself is left,
because its create API (`w.genie.create_space`) requires an undocumented `serialized_space` blob
(preview). The UI path below is reliable.

## What you should already have (from `databricks_setup.py`)
- Workspace: `https://<workspace-host>.azuredatabricks.net`
- Serverless SQL Warehouse: **`maf-demo-serverless`**
- Catalog/schema: **`<your_catalog>.default`**
- Table: `<your_catalog>.default.demo_sales` (row-level security applied via `demo_sales_rls`)

## Option A - Databricks UI (recommended)
1. Open `https://<workspace-host>.azuredatabricks.net`
2. Left nav -> **Genie** -> **New**.
3. **Connect data**: pick warehouse `maf-demo-serverless` and add the `demo_sales` table.
4. Name it `maf-demo-genie`. Save.
5. Copy the **space id** from the URL: `.../genie/rooms/<SPACE_ID>`.

## Option B - SDK (if you can supply the serialized_space schema)
`w.genie.create_space(warehouse_id, serialized_space, *, title=...)` exists but the
`serialized_space` format is undocumented/preview. If you export an existing space you can adapt it.

## After creation
```powershell
azd env set DATABRICKS_GENIE_SPACE_ID <SPACE_ID>
```
Managed MCP endpoint becomes:
`https://<workspace-host>.azuredatabricks.net/api/2.0/mcp/genie/<SPACE_ID>`

## Grant the LIMITED user access to the space + warehouse (required!)
The space owner (the admin) has access implicitly. The limited user needs explicit grants or their
tool calls fail (which otherwise surfaces as a hosted 500). In addition to the Unity Catalog grants
from `databricks_setup.py`, grant:
- **Genie space**: `CAN_RUN` (permissions object type `genie`, id = space id).
- **SQL warehouse** `maf-demo-serverless`: `CAN_USE`.

SDK example:
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel
from databricks.sdk.service.sql import WarehouseAccessControlRequest, WarehousePermissionLevel

w = WorkspaceClient(
    host="https://<workspace-host>.azuredatabricks.net",
    azure_workspace_resource_id="<workspace-resource-id>",
)
w.permissions.update(
    request_object_type="genie", request_object_id="<SPACE_ID>",
    access_control_list=[AccessControlRequest(
        user_name="<limited-user@example.com>", permission_level=PermissionLevel.CAN_RUN)])
w.warehouses.update_permissions(
    warehouse_id="<WAREHOUSE_ID>",
    access_control_list=[WarehouseAccessControlRequest(
        user_name="<limited-user@example.com>", permission_level=WarehousePermissionLevel.CAN_USE)])
```

## RBAC validation (do before wiring the agent)
- As the **admin user**: Genie answers over `demo_sales` and returns all rows (all regions).
- As the **limited user**: the row filter restricts results to a subset (e.g. one region).
  This is the per-user Unity Catalog RBAC the agent inherits via OAuth identity passthrough.
