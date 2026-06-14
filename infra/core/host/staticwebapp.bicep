param location string
param tags object
param name string
param keyVaultName string

resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    stagingEnvironmentPolicy: 'Enabled'
    allowConfigFileUpdates: true
    provider: 'None'
    enterpriseGradeCdnStatus: 'Disabled'
  }
}

// Store the deployment API key securely in Key Vault — do NOT expose it as a Bicep output
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource swaApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'swa-api-key'
  properties: {
    value: staticWebApp.listSecrets().properties.apiKey
  }
}

output id string = staticWebApp.id
output name string = staticWebApp.name
output defaultHostname string = staticWebApp.properties.defaultHostname
