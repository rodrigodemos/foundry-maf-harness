// connections.bicep - Foundry project connection to the Databricks Genie managed MCP server,
// using OAuth identity passthrough (custom OAuth) so the signed-in user's identity reaches
// Unity Catalog (per-user RBAC).
//
// !! BEST-EFFORT SCHEMA !!
// The ARM schema for MCP OAuth-identity-passthrough connections is not fully documented at time of
// writing. The exact `category`, `authType`, and credential shape may differ from what's below.
// If `az deployment` rejects this resource, create the connection via the Foundry portal or SDK
// instead (see scripts/ and the README deployment steps), then keep this file updated to match.
//
// References:
//   - MCP auth (OAuth identity passthrough): learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication

@description('Foundry (Cognitive Services) account name.')
param accountName string

@description('Foundry project name.')
param projectName string

@description('Connection resource name.')
param connectionName string

@description('Databricks Genie managed MCP URL: https://<ws>/api/2.0/mcp/genie/<space-id>')
param genieMcpUrl string

@description('Custom OAuth app client id.')
param oauthClientId string

@description('Custom OAuth authorize URL.')
param oauthAuthUrl string

@description('Custom OAuth token URL.')
param oauthTokenUrl string

@description('OAuth scopes (space-separated).')
param oauthScopes string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName

  resource project 'projects@2025-06-01' existing = {
    name: projectName
  }
}

// Category "RemoteTool" + OAuth identity passthrough for a remote MCP server.
resource mcpConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: account::project
  name: connectionName
  properties: {
    category: 'RemoteTool'
    target: genieMcpUrl
    // OAuth identity passthrough (custom OAuth). Field names below are best-effort.
    authType: 'OAuth2'
    metadata: {
      mcp: 'true'
      identityPassthrough: 'true'
      oauthClientId: oauthClientId
      oauthAuthUrl: oauthAuthUrl
      oauthTokenUrl: oauthTokenUrl
      oauthScopes: oauthScopes
    }
  }
}

output connectionId string = mcpConnection.id
output connectionName string = mcpConnection.name
