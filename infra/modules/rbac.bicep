@description('Foundry アカウント名')
param foundryAccountName string

@description('Foundry プロジェクト名')
param foundryProjectName string

@description('ACR リソース名')
param acrName string

@description('API Container App の System Assigned MI principalId')
param apiPrincipalId string

@description('UI Container App の System Assigned MI principalId')
param uiPrincipalId string

var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var azureAIUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// ── 既存リソース参照 ──
resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: foundryAccount
  name: foundryProjectName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

// ── AcrPull: API ──
resource acrPullApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, apiPrincipalId, acrPullRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── AcrPull: UI ──
resource acrPullUi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, uiPrincipalId, acrPullRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: uiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── Cognitive Services User: API のみ ──
resource foundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryAccount
  name: guid(foundryAccount.id, apiPrincipalId, cognitiveServicesUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── Azure AI User: API のみ ──
resource foundryProjectRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryProject
  name: guid(foundryProject.id, apiPrincipalId, azureAIUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAIUserRoleId)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}
