param location string
param tags object
param name string
param keyVaultName string

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: false   // Use managed identity / service principal — not admin credentials
    publicNetworkAccess: 'Enabled'
    zoneRedundancy: 'Disabled'
  }
}

// Store the login server URL in Key Vault for reference by other services
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource acrLoginServerSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'acr-login-server'
  properties: {
    value: acr.properties.loginServer
  }
}

output id string = acr.id
output name string = acr.name
output loginServer string = acr.properties.loginServer
