param location string
param tags object
param name string
param keyVaultName string

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: { defaultAction: 'Allow', bypass: 'AzureServices' }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

// Containers for CognitOps
resource equipmentImagesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'equipment-images'
  properties: { publicAccess: 'None' }
}

resource maintenanceManualsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'maintenance-manuals'
  properties: { publicAccess: 'None' }
}

resource sopDocumentsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'sop-documents'
  properties: { publicAccess: 'None' }
}

resource serviceReportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'service-reports'
  properties: { publicAccess: 'None' }
}

resource auditLogsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'audit-logs'
  properties: { publicAccess: 'None' }
}

// Store storage key in Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource storageKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'storage-account-key'
  properties: { value: storage.listKeys().keys[0].value }
}

output id string = storage.id
output name string = storage.name
output primaryEndpoint string = storage.properties.primaryEndpoints.blob
output keySecretUri string = storageKeySecret.properties.secretUri
