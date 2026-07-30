"""Provision Databricks assets for the sample (idempotent-ish).

What it does (as the signed-in Azure user, who must be a Databricks workspace + metastore admin):
  1. Ensures a serverless SQL Warehouse exists (Genie requires one).
  2. Creates a sample Unity Catalog table  <catalog>.<schema>.demo_sales  with a few rows.
  3. Applies per-user grants + a row filter to demonstrate RBAC:
       - ADMIN user   (--admin-user):   full SELECT, sees all rows.
       - LIMITED user (--limited-user): SELECT on the same table, but a Unity Catalog row filter
         restricts them to a subset of rows (e.g. one region) so "allowed vs denied" is provable.

Prereqs:
    az login   (as the admin user)
    uv sync --extra scripts        # installs databricks-sdk
Run:
    uv run python scripts/databricks_setup.py \
        --workspace-url https://<workspace-host>.azuredatabricks.net \
        --workspace-resource-id /subscriptions/<sub-id>/.../workspaces/<workspace> \
        --catalog <your_catalog> --schema default \
        --admin-user <admin-user@example.com> \
        --limited-user <limited-user@example.com>

NOTE: Creating the Genie *space* is a workspace UI/CLI action - see scripts/genie_space_setup.md.
"""

from __future__ import annotations

import argparse
import sys
import time


def log(msg: str) -> None:
    print(f"[databricks_setup] {msg}", flush=True)


def get_client(workspace_url: str, workspace_resource_id: str | None):
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        sys.exit("databricks-sdk not installed. Run: uv sync --extra scripts")

    kwargs = {"host": workspace_url}
    if workspace_resource_id:
        # Forces Azure AD auth against this workspace using the current az login.
        kwargs["azure_workspace_resource_id"] = workspace_resource_id
    return WorkspaceClient(**kwargs)


def ensure_warehouse(w, name: str) -> str:
    from databricks.sdk.service.sql import CreateWarehouseRequestWarehouseType, EndpointInfoWarehouseType

    for wh in w.warehouses.list():
        if wh.name == name:
            log(f"SQL warehouse '{name}' already exists (id={wh.id}).")
            return wh.id

    log(f"Creating serverless SQL warehouse '{name}' ...")
    created = w.warehouses.create(
        name=name,
        cluster_size="2X-Small",
        max_num_clusters=1,
        auto_stop_mins=10,
        enable_serverless_compute=True,
        warehouse_type=CreateWarehouseRequestWarehouseType.PRO,
    ).result()
    log(f"Created warehouse id={created.id}")
    return created.id


def ensure_user(w, email: str) -> bool:
    """Ensure the Entra user exists as a Databricks workspace user (SCIM). Returns True if present."""
    from databricks.sdk.service import iam

    for u in w.users.list(filter=f'userName eq "{email}"'):
        log(f"User '{email}' already present.")
        return True
    try:
        w.users.create(user_name=email)
        log(f"Provisioned workspace user '{email}'.")
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: could not provision '{email}' ({exc}). Grants for this user will be skipped.")
        return False


def run_sql(w, warehouse_id: str, statement: str, catalog: str, schema: str) -> None:
    from databricks.sdk.service.sql import StatementState

    log(f"SQL> {statement.splitlines()[0][:100]} ...")
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        catalog=catalog,
        schema=schema,
        wait_timeout="50s",
    )
    # Poll if still running.
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status and resp.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"SQL failed: {resp.status.state} - {getattr(resp.status, 'error', None)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-url", required=True)
    ap.add_argument("--workspace-resource-id", default=None)
    ap.add_argument("--catalog", default="main")
    ap.add_argument("--schema", default="default")
    ap.add_argument("--warehouse-name", default="maf-demo-serverless")
    ap.add_argument("--admin-user", required=True, help="User who should see ALL rows")
    ap.add_argument("--limited-user", required=True, help="User restricted by the row filter")
    args = ap.parse_args()

    w = get_client(args.workspace_url, args.workspace_resource_id)
    cat, sch = args.catalog, args.schema

    warehouse_id = ensure_warehouse(w, args.warehouse_name)

    log("Creating sample table and view ...")
    run_sql(w, warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {cat}.{sch}", cat, sch)
    run_sql(
        w,
        warehouse_id,
        f"""
        CREATE OR REPLACE TABLE {cat}.{sch}.demo_sales (
            order_id   INT,
            region     STRING,
            product    STRING,
            amount_usd DECIMAL(10,2),
            order_date DATE
        )
        """,
        cat,
        sch,
    )
    run_sql(
        w,
        warehouse_id,
        f"""
        INSERT INTO {cat}.{sch}.demo_sales VALUES
            (1,'West','Widget', 1200.00, DATE'2026-01-15'),
            (2,'West','Gadget',  850.50, DATE'2026-02-03'),
            (3,'East','Widget',  430.00, DATE'2026-02-20'),
            (4,'East','Gizmo',  2100.75, DATE'2026-03-11'),
            (5,'North','Gadget', 640.25, DATE'2026-03-28')
        """,
        cat,
        sch,
    )
    # Per-user RBAC via Unity Catalog ROW-LEVEL SECURITY on a single table: the admin sees all
    # rows; everyone else only 'West'. This is cleaner than a separate overlapping view (which can
    # double-count in Genie). The filter uses current_user(), which is the signed-in user because
    # Genie runs the query on their behalf (OAuth pass-through).
    run_sql(
        w,
        warehouse_id,
        f"CREATE OR REPLACE FUNCTION {cat}.{sch}.demo_sales_rls(region STRING) "
        f"RETURN current_user() = '{args.admin_user}' OR region = 'West'",
        cat,
        sch,
    )
    run_sql(
        w,
        warehouse_id,
        f"ALTER TABLE {cat}.{sch}.demo_sales SET ROW FILTER {cat}.{sch}.demo_sales_rls ON (region)",
        cat,
        sch,
    )

    log("Ensuring principals exist, then applying per-user Unity Catalog grants (proves RBAC) ...")
    ensure_user(w, args.admin_user)
    limited_ok = ensure_user(w, args.limited_user)

    admin_grants = [
        f"GRANT USE CATALOG ON CATALOG {cat} TO `{args.admin_user}`",
        f"GRANT USE SCHEMA ON SCHEMA {cat}.{sch} TO `{args.admin_user}`",
        f"GRANT SELECT ON TABLE {cat}.{sch}.demo_sales TO `{args.admin_user}`",
    ]
    # Limited user: SELECT on the SAME table; the row filter restricts them to West rows.
    limited_grants = [
        f"GRANT USE CATALOG ON CATALOG {cat} TO `{args.limited_user}`",
        f"GRANT USE SCHEMA ON SCHEMA {cat}.{sch} TO `{args.limited_user}`",
        f"GRANT SELECT ON TABLE {cat}.{sch}.demo_sales TO `{args.limited_user}`",
    ]
    for stmt in admin_grants:
        run_sql(w, warehouse_id, stmt, cat, sch)
    if limited_ok:
        for stmt in limited_grants:
            run_sql(w, warehouse_id, stmt, cat, sch)
    else:
        log(f"Skipped grants for '{args.limited_user}' (not provisioned). Add the user, then re-run.")

    log("Done.")
    log(f"  Warehouse id: {warehouse_id}")
    log(f"  Table:        {cat}.{sch}.demo_sales   (row-level security via demo_sales_rls)")
    log(f"  RBAC:         {args.admin_user} sees all rows; {args.limited_user} sees only West")
    log("Next: create a Genie space over ONLY demo_sales -> scripts/genie_space_setup.md")


if __name__ == "__main__":
    main()
