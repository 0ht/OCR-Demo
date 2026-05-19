@description('プロジェクト名')
param projectName string

@description('環境名')
param environment string

@description('Azure リージョン')
param location string

@description('共通タグ')
param tags object

@description('ACA Managed Environment ID')
param managedEnvironmentId string

param apiImage string
param uiImage string

param foundryEndpoint string
param foundryProjectName string
param analyzerId string
param contentUnderstandingApiVersion string
param documentIntelligenceModelId string
param documentIntelligenceApiVersion string

var apiName = 'ca-${projectName}-${environment}-api'
var uiName = 'ca-${projectName}-${environment}-ui'

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  tags: union(tags, {
    'azd-service-name': 'api'
  })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      ingress: {
        external: false
        targetPort: 8000
        transport: 'http'
      }
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          env: [
            {
              name: 'FOUNDRY_ENDPOINT'
              value: foundryEndpoint
            }
            {
              name: 'FOUNDRY_PROJECT_NAME'
              value: foundryProjectName
            }
            {
              name: 'CONTENT_UNDERSTANDING_ANALYZER_ID'
              value: analyzerId
            }
            {
              name: 'CONTENT_UNDERSTANDING_API_VERSION'
              value: contentUnderstandingApiVersion
            }
            {
              name: 'DOCUMENT_INTELLIGENCE_MODEL_ID'
              value: documentIntelligenceModelId
            }
            {
              name: 'DOCUMENT_INTELLIGENCE_API_VERSION'
              value: documentIntelligenceApiVersion
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
  name: uiName
  location: location
  tags: union(tags, {
    'azd-service-name': 'ui'
  })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
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

output apiName string = api.name
output uiName string = ui.name
output apiPrincipalId string = api.identity.principalId
output uiPrincipalId string = ui.identity.principalId
output apiEndpoint string = 'http://${api.properties.configuration.ingress.fqdn}'
output uiEndpoint string = 'https://${ui.properties.configuration.ingress.fqdn}'
