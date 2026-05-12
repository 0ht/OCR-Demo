@description('プロジェクト名')
param projectName string

@description('環境名')
param environment string

@description('Azure リージョン')
param location string

@description('共通タグ')
param tags object

@description('Foundry プロジェクト名')
param foundryProjectName string

@description('Private Endpoint 用サブネット ID')
param subnetPrivateEndpointsId string

@description('cognitiveservices ゾーン ID')
param privateDnsZoneCognitiveServicesId string

@description('openai ゾーン ID')
param privateDnsZoneOpenAIId string

@description('services.ai ゾーン ID')
param privateDnsZoneServicesAIId string

var foundryName = toLower('ai-${projectName}-${environment}-${take(uniqueString(resourceGroup().id), 6)}')

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: foundryName
  location: location
  tags: tags
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: foundryName
    publicNetworkAccess: 'Disabled'
    allowProjectManagement: true
    disableLocalAuth: true
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: foundryAccount
  name: foundryProjectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource peFoundry 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-${foundryName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnetPrivateEndpointsId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-foundry'
        properties: {
          privateLinkServiceId: foundryAccount.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource peFoundryDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: peFoundry
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices'
        properties: {
          privateDnsZoneId: privateDnsZoneCognitiveServicesId
        }
      }
      {
        name: 'openai'
        properties: {
          privateDnsZoneId: privateDnsZoneOpenAIId
        }
      }
      {
        name: 'services-ai'
        properties: {
          privateDnsZoneId: privateDnsZoneServicesAIId
        }
      }
    ]
  }
}

output accountName string = foundryAccount.name
output projectName string = foundryProject.name
output endpoint string = 'https://${foundryAccount.name}.services.ai.azure.com/'
