@description('プロジェクト名')
param projectName string

@description('環境名')
param environment string

@description('Azure リージョン')
param location string

@description('共通タグ')
param tags object

@description('Private Endpoint 用サブネット ID')
param subnetPrivateEndpointsId string

@description('ACR 用 Private DNS Zone ID')
param privateDnsZoneAcrId string

// ACR 名: ハイフン不可・小文字のみ・グローバル一意
var acrName = toLower('acr${replace(projectName, '-', '')}${environment}${take(uniqueString(resourceGroup().id), 6)}')

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Premium'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Disabled'
    networkRuleSet: {
      defaultAction: 'Deny'
    }
  }
}

resource peAcr 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-${acrName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnetPrivateEndpointsId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-acr'
        properties: {
          privateLinkServiceId: acr.id
          groupIds: [
            'registry'
          ]
        }
      }
    ]
  }
}

resource peAcrDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: peAcr
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'acr'
        properties: {
          privateDnsZoneId: privateDnsZoneAcrId
        }
      }
    ]
  }
}

output id string = acr.id
output name string = acr.name
output loginServer string = acr.properties.loginServer
