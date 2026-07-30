// rbac.bicep - role assignments for the deployed agent's Entra identity (autonomous/fallback path).
//
// IMPORTANT: Databricks Unity Catalog grants are NOT Azure RBAC - they live inside Databricks and
// are applied via SQL/SCIM (see scripts/databricks_setup.py), NOT here. This module only handles
// any *Azure ARM* role the agent identity may need (optional). By default it is a no-op unless you
// pass a roleDefinitionId.
//
// The agent identity does not exist until the first `azd up` / deploy creates it. Run this module
// as a second pass with `agentPrincipalId` set to the agent's Object (principal) id.

@description('Object (principal) id of the agent Entra identity.')
param agentPrincipalId string

@description('Optional Databricks workspace resource id (for an ARM role assignment, if desired).')
param databricksWorkspaceResourceId string = ''

@description('Optional role definition GUID to assign to the agent identity at RG scope. Empty = skip.')
param roleDefinitionId string = ''

var assignAtResourceGroup = !empty(roleDefinitionId) && empty(databricksWorkspaceResourceId)
var assignAtDatabricks = !empty(roleDefinitionId) && !empty(databricksWorkspaceResourceId)

resource rgAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignAtResourceGroup) {
  name: guid(resourceGroup().id, agentPrincipalId, roleDefinitionId)
  properties: {
    principalId: agentPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
  }
}

// If a Databricks workspace resource id is supplied, assign the role at that scope instead.
// (Kept for completeness; UC data access is still governed inside Databricks, not by this role.)
resource dbxWorkspace 'Microsoft.Databricks/workspaces@2024-05-01' existing = if (assignAtDatabricks) {
  name: last(split(databricksWorkspaceResourceId, '/'))
}

resource dbxAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignAtDatabricks) {
  name: guid(databricksWorkspaceResourceId, agentPrincipalId, roleDefinitionId)
  scope: dbxWorkspace
  properties: {
    principalId: agentPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
  }
}

output assigned bool = assignAtResourceGroup || assignAtDatabricks
