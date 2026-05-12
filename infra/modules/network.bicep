@description('プロジェクト名')
param projectName string

@description('環境名')
param environment string

@description('Azure リージョン')
param location string

@description('共通タグ')
param tags object

@description('VNet アドレス空間')
param vnetAddressPrefix string = '10.10.0.0/16'

@description('ACA インフラサブネット CIDR')
param acaSubnetPrefix string = '10.10.0.0/23'

@description('Private Endpoint サブネット CIDR')
param peSubnetPrefix string = '10.10.2.0/24'

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: 'vnet-${projectName}-${environment}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: 'aca-infra'
        properties: {
          addressPrefix: acaSubnetPrefix
          delegations: [
            {
              name: 'aca-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'pe-subnet'
        properties: {
          addressPrefix: peSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output acaSubnetId string = '${vnet.id}/subnets/aca-infra'
output peSubnetId string = '${vnet.id}/subnets/pe-subnet'
