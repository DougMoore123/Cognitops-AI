param location string
param tags object
param name string
param storageAccountId string
param keyVaultId string
param applicationInsightsId string
param openAiServiceId string
param searchServiceId string

resource foundryHub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'Hub'
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Basic', tier: 'Basic' }
  properties: {
    friendlyName: 'CognitOps AI Foundry Hub'
    description: 'Azure AI Foundry Hub for CognitOps AI Platform'
    storageAccount: storageAccountId
    keyVault: keyVaultId
    applicationInsights: applicationInsightsId
    publicNetworkAccess: 'Enabled'
  }
}

// Connect Azure OpenAI to the hub
resource openAiConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: foundryHub
  name: 'cognitops-openai'
  properties: {
    category: 'AzureOpenAI'
    target: reference(openAiServiceId, '2024-04-01-preview', 'Full').properties.endpoint
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: listKeys(openAiServiceId, '2024-04-01-preview').key1
    }
  }
}

// Connect Azure AI Search to the hub
resource searchConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: foundryHub
  name: 'cognitops-search'
  properties: {
    category: 'CognitiveSearch'
    target: 'https://${last(split(searchServiceId, '/'))}.search.windows.net'
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: listAdminKeys(searchServiceId, '2024-03-01-preview').primaryKey
    }
  }
}

output id string = foundryHub.id
output name string = foundryHub.name
output principalId string = foundryHub.identity.principalId
