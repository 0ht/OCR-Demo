@description('プロジェクト名 (リソース命名に使用)')
param projectName string

@description('環境名 (dev / stg / prod)')
@allowed([
  'dev'
  'stg'
  'prod'
])
param environment string

@description('Azure リージョン')
param location string = deployment().location

@description('既存または新規作成するリソースグループ名。未指定時は rg-{projectName}-{environment}')
param resourceGroupName string = ''

@description('Foundry プロジェクト名 (新版 Foundry の子リソース)')
param foundryProjectName string = 'default-project'

@description('Content Understanding で使用する prebuilt または custom analyzer ID')
param analyzerId string = 'prebuilt-read'

@description('Content Understanding REST API バージョン')
param contentUnderstandingApiVersion string = '2025-11-01'

@description('Document Intelligence で使用する prebuilt モデル ID')
param documentIntelligenceModelId string = 'prebuilt-read'

@description('Document Intelligence REST API バージョン')
param documentIntelligenceApiVersion string = '2024-11-30'

@description('API コンテナイメージ (azd が解決)')
param apiImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('UI コンテナイメージ (azd が解決)')
param uiImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

targetScope = 'subscription'

var rgName = empty(resourceGroupName) ? 'rg-${projectName}-${environment}' : resourceGroupName

var tags = {
  'azd-env-name': projectName
  project: projectName
  managed_by: 'azd'
  environment: environment
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
}

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  name: 'monitoring'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
  }
}

module network 'modules/network.bicep' = {
  scope: rg
  name: 'network'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
  }
}

module dns 'modules/privateDns.bicep' = {
  scope: rg
  name: 'privateDns'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
    vnetId: network.outputs.vnetId
  }
}

module acr 'modules/acr.bicep' = {
  scope: rg
  name: 'acr'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
    subnetPrivateEndpointsId: network.outputs.peSubnetId
    privateDnsZoneAcrId: dns.outputs.acrZoneId
  }
}

module foundry 'modules/foundry.bicep' = {
  scope: rg
  name: 'foundry'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
    foundryProjectName: foundryProjectName
    subnetPrivateEndpointsId: network.outputs.peSubnetId
    privateDnsZoneCognitiveServicesId: dns.outputs.cognitiveServicesZoneId
    privateDnsZoneOpenAIId: dns.outputs.openAIZoneId
    privateDnsZoneServicesAIId: dns.outputs.servicesAIZoneId
  }
}

module containerEnv 'modules/containerEnv.bicep' = {
  scope: rg
  name: 'containerEnv'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
    infrastructureSubnetId: network.outputs.acaSubnetId
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
  }
}

module containerApps 'modules/containerApps.bicep' = {
  scope: rg
  name: 'containerApps'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
    managedEnvironmentId: containerEnv.outputs.managedEnvironmentId
    apiImage: apiImage
    uiImage: uiImage
    foundryEndpoint: foundry.outputs.endpoint
    foundryProjectName: foundry.outputs.projectName
    analyzerId: analyzerId
    contentUnderstandingApiVersion: contentUnderstandingApiVersion
    documentIntelligenceModelId: documentIntelligenceModelId
    documentIntelligenceApiVersion: documentIntelligenceApiVersion
  }
}

module rbac 'modules/rbac.bicep' = {
  scope: rg
  name: 'rbac'
  params: {
    acrName: acr.outputs.name
    foundryAccountName: foundry.outputs.accountName
    foundryProjectName: foundry.outputs.projectName
    apiPrincipalId: containerApps.outputs.apiPrincipalId
    uiPrincipalId: containerApps.outputs.uiPrincipalId
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_NAME string = acr.outputs.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.outputs.loginServer
output FOUNDRY_ENDPOINT string = foundry.outputs.endpoint
output FOUNDRY_ACCOUNT_NAME string = foundry.outputs.accountName
output FOUNDRY_PROJECT_NAME string = foundry.outputs.projectName
output SERVICE_API_NAME string = containerApps.outputs.apiName
output SERVICE_UI_NAME string = containerApps.outputs.uiName
output SERVICE_UI_ENDPOINT string = containerApps.outputs.uiEndpoint
output SERVICE_API_INTERNAL_ENDPOINT string = containerApps.outputs.apiEndpoint
