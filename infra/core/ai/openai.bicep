param location string
param tags object
param name string
param keyVaultName string
param principalId string = ''

// GPT-4o supports multimodal (vision + text)
var gpt4oDeploymentName = 'gpt-4o'
var embeddingDeploymentName = 'text-embedding-3-large'

resource openAI 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    networkAcls: { defaultAction: 'Allow' }
    disableLocalAuth: false
  }
}

// GPT-4o deployment – multimodal LLM (vision + text + reasoning)
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAI
  name: gpt4oDeploymentName
  sku: { name: 'GlobalStandard', capacity: 30 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

// text-embedding-3-large for RAG vector embeddings
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAI
  name: embeddingDeploymentName
  dependsOn: [gpt4oDeployment]
  sku: { name: 'Standard', capacity: 120 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

// Grant Cognitive Services OpenAI User role to principal
resource principalRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: openAI
  name: guid(openAI.id, principalId, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
    principalType: 'User'
  }
}

// Store OpenAI API key in Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource openAiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'openai-api-key'
  properties: { value: openAI.listKeys().key1 }
}

output id string = openAI.id
output name string = openAI.name
output endpoint string = openAI.properties.endpoint
output keySecretUri string = openAiKeySecret.properties.secretUri
output gpt4oDeploymentName string = gpt4oDeploymentName
output embeddingDeploymentName string = embeddingDeploymentName
