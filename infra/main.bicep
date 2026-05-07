param location string = resourceGroup().location
param environmentName string

param apiImage string
param uiImage string

param documentIntelligenceEndpoint string
@secure()
param documentIntelligenceKey string
param documentIntelligenceModelId string = 'prebuilt-read'

param contentUnderstandingEndpoint string
@secure()
param contentUnderstandingKey string
param contentUnderstandingProject string
param contentUnderstandingApiVersion string = '2024-12-01-preview'

var tags = {
  'azd-env-name': environmentName
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${environmentName}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: 'vnet-${environmentName}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.10.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'aca-infra'
        properties: {
          addressPrefix: '10.10.0.0/23'
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
    ]
  }
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'acae-${environmentName}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: listKeys(logAnalytics.id, logAnalytics.apiVersion).primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/aca-infra'
      internal: true
    }
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'api-${environmentName}'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      ingress: {
        external: false
        targetPort: 8000
        transport: 'http'
      }
      secrets: [
        {
          name: 'document-intelligence-key'
          value: documentIntelligenceKey
        }
        {
          name: 'content-understanding-key'
          value: contentUnderstandingKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          env: [
            {
              name: 'DOCUMENT_INTELLIGENCE_ENDPOINT'
              value: documentIntelligenceEndpoint
            }
            {
              name: 'DOCUMENT_INTELLIGENCE_MODEL_ID'
              value: documentIntelligenceModelId
            }
            {
              name: 'DOCUMENT_INTELLIGENCE_KEY'
              secretRef: 'document-intelligence-key'
            }
            {
              name: 'CONTENT_UNDERSTANDING_ENDPOINT'
              value: contentUnderstandingEndpoint
            }
            {
              name: 'CONTENT_UNDERSTANDING_PROJECT'
              value: contentUnderstandingProject
            }
            {
              name: 'CONTENT_UNDERSTANDING_API_VERSION'
              value: contentUnderstandingApiVersion
            }
            {
              name: 'CONTENT_UNDERSTANDING_KEY'
              secretRef: 'content-understanding-key'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource ui 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ui-${environmentName}'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8501
        transport: 'http'
      }
    }
    template: {
      containers: [
        {
          name: 'ui'
          image: uiImage
          env: [
            {
              name: 'API_BASE_URL'
              value: 'https://${api.properties.configuration.ingress.fqdn}'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output SERVICE_UI_ENDPOINT string = 'https://${ui.properties.configuration.ingress.fqdn}'
output SERVICE_API_INTERNAL_ENDPOINT string = 'https://${api.properties.configuration.ingress.fqdn}'
