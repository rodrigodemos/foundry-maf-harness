<#
.SYNOPSIS
    Fallback - register an Entra app for Databricks OAuth passthrough via the AzureDatabricks
    first-party resource.

.DESCRIPTION
    Use this ONLY if the Databricks-native OIDC custom OAuth app (databricks_oauth_app.py) is not
    viable. This registers an Entra app with delegated permission to the AzureDatabricks resource
    (2ff814a6-3304-4ab8-85cb-cd0e6f879c1d / user_impersonation) and grants tenant admin consent.

    WARNING: Foundry may reject Microsoft-audience tokens to third-party MCP endpoints
    ("Cannot pass Microsoft token to untrusted MCP endpoint"). Prefer the Databricks-native path.

.NOTES
    [manual] Requires permission to register an app AND grant tenant admin consent.
    Requires: az login  (Application Administrator / Privileged Role Administrator for consent).
#>
param(
    [string]$DisplayName = "maf-orchestrator-databricks-passthrough",
    [string[]]$RedirectUris = @("https://localhost/placeholder-replace-after-connection"),
    [switch]$GrantAdminConsent
)

$ErrorActionPreference = "Stop"

# AzureDatabricks first-party app + user_impersonation delegated permission id.
$AzureDatabricksAppId = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
$UserImpersonationId  = "739272be-e143-11e8-9f32-f2801f1b9fd1"  # AzureDatabricks user_impersonation

Write-Host "Registering Entra app '$DisplayName' ..."
$app = az ad app create `
    --display-name $DisplayName `
    --web-redirect-uris $RedirectUris `
    --required-resource-accesses "[{\"resourceAppId\":\"$AzureDatabricksAppId\",\"resourceAccess\":[{\"id\":\"$UserImpersonationId\",\"type\":\"Scope\"}]}]" `
    | ConvertFrom-Json

$appId = $app.appId
Write-Host "  appId (client_id): $appId"

# Service principal + client secret
az ad sp create --id $appId | Out-Null
$secret = az ad app credential reset --id $appId --years 1 --query password -o tsv
Write-Host "  client_secret: $secret   (store securely - shown once)"

Write-Host "  auth_url : https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/authorize"
Write-Host "  token_url: https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token"
Write-Host "  scopes   : $AzureDatabricksAppId/user_impersonation offline_access"

if ($GrantAdminConsent) {
    Write-Host "Granting tenant admin consent ... [manual: requires privileged role]"
    az ad app permission admin-consent --id $appId
    Write-Host "Admin consent granted."
} else {
    Write-Host "`nRe-run with -GrantAdminConsent (as a privileged admin) to consent, or consent in the portal."
}
