using './main.bicep'

// Existing Foundry resources (already provisioned in the target subscription).
param accountName = '<foundry-account-name>'
param projectName = '<foundry-project-name>'

// Databricks workspace.
param databricksWorkspaceUrl = 'https://<workspace-host>.azuredatabricks.net'
param databricksWorkspaceResourceId = '/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Databricks/workspaces/<workspace>'

// Set after the Genie space and the custom OAuth app exist. Empty values skip the connection
// module so the rest of the deployment still succeeds.
param genieSpaceId = ''
param mcpConnectionName = 'databricks-genie-mcp'
param oauthClientId = ''
param oauthAuthUrl = 'https://<workspace-host>.azuredatabricks.net/oidc/v1/authorize'
param oauthTokenUrl = 'https://<workspace-host>.azuredatabricks.net/oidc/v1/token'
param oauthScopes = 'all-apis offline_access'

// Set after the first deploy to run the RBAC pass for the agent's Entra identity.
param agentPrincipalId = ''
