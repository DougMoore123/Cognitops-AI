param location string
param tags object
param accountName string
param keyVaultName string
param principalId string = ''

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    databaseAccountOfferType: 'Standard'
    enableFreeTier: false
    enableAnalyticalStorage: false
    isVirtualNetworkFilterEnabled: false
    publicNetworkAccess: 'Enabled'
    locations: [{ locationName: location, failoverPriority: 0 }]
    capabilities: [{ name: 'EnableServerless' }]
    backupPolicy: { type: 'Continuous', continuousModeProperties: { tier: 'Continuous7Days' } }
  }
}

resource cognitopsDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosAccount
  name: 'cognitops'
  properties: { resource: { id: 'cognitops' } }
}

resource serviceTicketsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cognitopsDb
  name: 'service-tickets'
  properties: {
    resource: {
      id: 'service-tickets'
      partitionKey: { paths: ['/equipmentId'], kind: 'Hash' }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [{ path: '/*' }]
      }
    }
  }
}

resource workOrdersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cognitopsDb
  name: 'work-orders'
  properties: {
    resource: {
      id: 'work-orders'
      partitionKey: { paths: ['/technicianId'], kind: 'Hash' }
    }
  }
}

resource escalationsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cognitopsDb
  name: 'escalations'
  properties: {
    resource: {
      id: 'escalations'
      partitionKey: { paths: ['/supervisorId'], kind: 'Hash' }
    }
  }
}

resource equipmentProfilesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cognitopsDb
  name: 'equipment-profiles'
  properties: {
    resource: {
      id: 'equipment-profiles'
      partitionKey: { paths: ['/facilityId'], kind: 'Hash' }
    }
  }
}

resource auditLogsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: cognitopsDb
  name: 'audit-logs'
  properties: {
    resource: {
      id: 'audit-logs'
      partitionKey: { paths: ['/date'], kind: 'Hash' }
      defaultTtl: 7776000 // 90 days
    }
  }
}

// Role assignment: Cosmos DB Built-in Data Contributor for principal
resource cosmosRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-02-15-preview' = if (!empty(principalId)) {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, principalId, '00000000-0000-0000-0000-000000000002')
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: principalId
    scope: cosmosAccount.id
  }
}

// Store connection string in Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource cosmosKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cosmos-connection-string'
  properties: { value: cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString }
}

output id string = cosmosAccount.id
output endpoint string = cosmosAccount.properties.documentEndpoint
output keySecretUri string = cosmosKeySecret.properties.secretUri
output databaseName string = cognitopsDb.name
