param location string
param tags object
param environmentId string
param applicationInsightsConnectionString string
param openAiEndpoint string
param openAiKeySecretUri string
param searchEndpoint string
param searchKeySecretUri string
param cosmosEndpoint string
param cosmosKeySecretUri string
param serviceBusNamespace string
param serviceBusConnectionSecretUri string
param storageAccountName string
param storageKeySecretUri string
param keyVaultName string
param foundryProjectEndpoint string

// Images start as placeholder. After infra deploy, build with:
//   az acr build --registry <acrName> --image cognitops/<service>:latest src/<service>

var sharedEnv = [
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING',  value: applicationInsightsConnectionString }
  { name: 'AZURE_OPENAI_ENDPOINT',                  value: openAiEndpoint }
  { name: 'AZURE_AI_SEARCH_ENDPOINT',               value: searchEndpoint }
  { name: 'AZURE_COSMOS_ENDPOINT',                  value: cosmosEndpoint }
  { name: 'AZURE_SERVICE_BUS_NAMESPACE',            value: serviceBusNamespace }
  { name: 'AZURE_STORAGE_ACCOUNT_NAME',             value: storageAccountName }
  { name: 'AZURE_FOUNDRY_PROJECT_ENDPOINT',         value: foundryProjectEndpoint }
  { name: 'AZURE_KEY_VAULT_NAME',                   value: keyVaultName }
  { name: 'AZURE_OPENAI_API_KEY',                   secretRef: 'openai-api-key' }
  { name: 'AZURE_AI_SEARCH_API_KEY',                secretRef: 'search-admin-key' }
  { name: 'AZURE_COSMOS_CONNECTION_STRING',         secretRef: 'cosmos-connection-string' }
  { name: 'AZURE_SERVICE_BUS_CONNECTION_STRING',    secretRef: 'servicebus-connection-string' }
  { name: 'AZURE_STORAGE_KEY',                      secretRef: 'storage-account-key' }
]

var secretRefs = [
  { name: 'openai-api-key',              keyVaultUrl: openAiKeySecretUri,               identity: 'system' }
  { name: 'search-admin-key',            keyVaultUrl: searchKeySecretUri,               identity: 'system' }
  { name: 'cosmos-connection-string',    keyVaultUrl: cosmosKeySecretUri,               identity: 'system' }
  { name: 'servicebus-connection-string',keyVaultUrl: serviceBusConnectionSecretUri,    identity: 'system' }
  { name: 'storage-account-key',         keyVaultUrl: storageKeySecretUri,              identity: 'system' }
]

resource orchestratorApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-orchestrator'
  location: location
  tags: union(tags, { 'azd-service-name': 'orchestrator' })
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: environmentId
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'http' }
      secrets: secretRefs
    }
    template: {
      containers: [{
        name: 'orchestrator'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        resources: { cpu: json('0.5'), memory: '1.0Gi' }
        env: sharedEnv
      }]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
}

resource ragServiceApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-rag-service'
  location: location
  tags: union(tags, { 'azd-service-name': 'rag-service' })
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: environmentId
    configuration: {
      ingress: { external: false, targetPort: 8001, transport: 'http' }
      secrets: secretRefs
    }
    template: {
      containers: [{
        name: 'rag-service'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        resources: { cpu: json('0.5'), memory: '1.0Gi' }
        env: sharedEnv
      }]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
}

resource diagnosticEngineApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-diagnostic-engine'
  location: location
  tags: union(tags, { 'azd-service-name': 'diagnostic-engine' })
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: environmentId
    configuration: {
      ingress: { external: false, targetPort: 8002, transport: 'http' }
      secrets: secretRefs
    }
    template: {
      containers: [{
        name: 'diagnostic-engine'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        resources: { cpu: json('1.0'), memory: '2.0Gi' }
        env: sharedEnv
      }]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
}

resource severityScorerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-severity-scorer'
  location: location
  tags: union(tags, { 'azd-service-name': 'severity-scorer' })
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: environmentId
    configuration: {
      ingress: { external: false, targetPort: 8003, transport: 'http' }
      secrets: secretRefs
    }
    template: {
      containers: [{
        name: 'severity-scorer'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        resources: { cpu: json('0.5'), memory: '1.0Gi' }
        env: sharedEnv
      }]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

resource reportGeneratorApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-report-generator'
  location: location
  tags: union(tags, { 'azd-service-name': 'report-generator' })
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: environmentId
    configuration: {
      ingress: { external: false, targetPort: 8004, transport: 'http' }
      secrets: secretRefs
    }
    template: {
      containers: [{
        name: 'report-generator'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        resources: { cpu: json('0.5'), memory: '1.0Gi' }
        env: sharedEnv
      }]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

resource supervisorApiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-supervisor-api'
  location: location
  tags: union(tags, { 'azd-service-name': 'supervisor-api' })
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: environmentId
    configuration: {
      ingress: { external: true, targetPort: 8005, transport: 'http' }
      secrets: secretRefs
    }
    template: {
      containers: [{
        name: 'supervisor-api'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        resources: { cpu: json('0.5'), memory: '1.0Gi' }
        env: sharedEnv
      }]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// Key Vault access for system-assigned identities
resource kvRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = { name: keyVaultName }

resource orchKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kvRef
  name: guid(kvRef.id, orchestratorApp.id, 'kv-secrets-user')
  properties: {
    principalId: orchestratorApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalType: 'ServicePrincipal'
  }
}

resource ragKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kvRef
  name: guid(kvRef.id, ragServiceApp.id, 'kv-secrets-user')
  properties: {
    principalId: ragServiceApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalType: 'ServicePrincipal'
  }
}

resource diagKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kvRef
  name: guid(kvRef.id, diagnosticEngineApp.id, 'kv-secrets-user')
  properties: {
    principalId: diagnosticEngineApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalType: 'ServicePrincipal'
  }
}

resource sevKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kvRef
  name: guid(kvRef.id, severityScorerApp.id, 'kv-secrets-user')
  properties: {
    principalId: severityScorerApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalType: 'ServicePrincipal'
  }
}

resource repKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kvRef
  name: guid(kvRef.id, reportGeneratorApp.id, 'kv-secrets-user')
  properties: {
    principalId: reportGeneratorApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalType: 'ServicePrincipal'
  }
}

resource supKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kvRef
  name: guid(kvRef.id, supervisorApiApp.id, 'kv-secrets-user')
  properties: {
    principalId: supervisorApiApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalType: 'ServicePrincipal'
  }
}

output orchestratorUrl string = 'https://${orchestratorApp.properties.configuration.ingress.fqdn}'
output ragServiceUrl string = 'https://${ragServiceApp.properties.configuration.ingress.fqdn}'
output diagnosticEngineUrl string = 'https://${diagnosticEngineApp.properties.configuration.ingress.fqdn}'
output supervisorApiUrl string = 'https://${supervisorApiApp.properties.configuration.ingress.fqdn}'
