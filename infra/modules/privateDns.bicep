@description('プロジェクト名')
param projectName string

@description('環境名')
param environment string

@description('Azure リージョン (Private DNS Zone は global だが location は引数で受け取り未使用)')
param location string

@description('共通タグ')
param tags object

@description('VNet にリンクする対象 ID')
param vnetId string

var zoneNames = [
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
  'privatelink.azurecr.io'
]

resource zones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zone in zoneNames: {
  name: zone
  location: 'global'
  tags: tags
}]

resource vnetLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zone, i) in zoneNames: {
  parent: zones[i]
  name: 'link-${projectName}-${environment}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}]

output cognitiveServicesZoneId string = zones[0].id
output openAIZoneId string = zones[1].id
output servicesAIZoneId string = zones[2].id
output acrZoneId string = zones[3].id
