// main.bicep - resource-group-scoped deployment for the maf-orchestrator hosted agent.
//
// Scope: the resource group that holds the Foundry account.
// This template does NOT provision the project, model, ACR, or App Insights - those already exist.
// It wires the pieces that ARE declarative:
//   1. connections.bicep - a project connection fronting the Databricks Genie managed MCP server
//                          with OAuth identity passthrough (per-user RBAC). [best-effort schema]
//   2. rbac.bicep        - role assignments for the agent's Entra identity (autonomous/fallback
//                          path). Applied AFTER first deploy once the agentIdentityId exists.
//
// Deploy (example):
//   az deployment group create -g <resource-group> -f deploy/databricks/main.bicep -p deploy/databricks/main.bicepparam

targetScope = 'resourceGroup'

@description('Foundry (Cognitive Services) account name.')
param accountName string

@description('Foundry project name.')
param projectName string

@description('Databricks workspace host URL, e.g. https://<workspace-host>.azuredatabricks.net')
param databricksWorkspaceUrl string

@description('Databricks Genie space id. Leave empty to skip creating the MCP connection.')
param genieSpaceId string = ''

@description('Name for the Databricks Genie MCP project connection.')
param mcpConnectionName string = 'databricks-genie-mcp'

@description('Custom OAuth app client id for Databricks passthrough.')
param oauthClientId string = ''

@description('Custom OAuth authorize URL (Databricks OIDC).')
param oauthAuthUrl string = ''

@description('Custom OAuth token URL (Databricks OIDC).')
param oauthTokenUrl string = ''

@description('OAuth scopes (space-separated). Include offline_access for refresh.')
param oauthScopes string = 'all-apis offline_access'

@description('Object (principal) id of the deployed agent Entra identity. Empty on first deploy.')
param agentPrincipalId string = ''

@description('Databricks workspace resource id for the fallback RBAC assignment. Optional.')
param databricksWorkspaceResourceId string = ''

var deployConnection = !empty(genieSpaceId) && !empty(oauthClientId)
var deployRbac = !empty(agentPrincipalId)

module connection 'modules/connections.bicep' = if (deployConnection) {
  name: 'databricks-genie-mcp-connection'
  params: {
    accountName: accountName
    projectName: projectName
    connectionName: mcpConnectionName
    genieMcpUrl: '${databricksWorkspaceUrl}/api/2.0/mcp/genie/${genieSpaceId}'
    oauthClientId: oauthClientId
    oauthAuthUrl: oauthAuthUrl
    oauthTokenUrl: oauthTokenUrl
    oauthScopes: oauthScopes
  }
}

module rbac 'modules/rbac.bicep' = if (deployRbac) {
  name: 'agent-identity-rbac'
  params: {
    agentPrincipalId: agentPrincipalId
    databricksWorkspaceResourceId: databricksWorkspaceResourceId
  }
}

output connectionDeployed bool = deployConnection
output rbacDeployed bool = deployRbac
