param location string
param tags object
param name string
param keyVaultName string
param principalId string = ''

@description('SKU for AI Search - Standard supports vector search and semantic ranking')
param sku string = 'standard'

resource searchService 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: { name: sku }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    semanticSearch: 'standard'
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http403' } }
  }
}

// Grant Search Index Data Contributor to principal
resource principalRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: searchService
  name: guid(searchService.id, principalId, '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7') // Search Index Data Contributor
    principalType: 'User'
  }
}

// Store search admin key in Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource searchKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'search-admin-key'
  properties: { value: searchService.listAdminKeys().primaryKey }
}

output id string = searchService.id
output name string = searchService.name
output endpoint string = 'https://${searchService.name}.search.windows.net'
output keySecretUri string = searchKeySecret.properties.secretUri
