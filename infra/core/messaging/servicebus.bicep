param location string
param tags object
param name string
param keyVaultName string

resource sbNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard' }
  properties: {
    minimumTlsVersion: '1.2'
    disableLocalAuth: false
    publicNetworkAccess: 'Enabled'
  }
}

// Queues for CognitOps workflow
resource escalationQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'escalation-queue'
  properties: {
    lockDuration: 'PT5M'
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: false
    requiresSession: false
    defaultMessageTimeToLive: 'P7D'
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 5
  }
}

resource supervisorReviewQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'supervisor-review-queue'
  properties: {
    lockDuration: 'PT10M'
    maxSizeInMegabytes: 1024
    requiresSession: false
    defaultMessageTimeToLive: 'P14D'
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 3
  }
}

resource diagnosticResultsTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'diagnostic-results'
  properties: {
    defaultMessageTimeToLive: 'P1D'
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: false
  }
}

resource reportGeneratorSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: diagnosticResultsTopic
  name: 'report-generator-sub'
  properties: {
    lockDuration: 'PT5M'
    defaultMessageTimeToLive: 'P1D'
    maxDeliveryCount: 5
  }
}

resource auditLogSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: diagnosticResultsTopic
  name: 'audit-log-sub'
  properties: {
    lockDuration: 'PT2M'
    defaultMessageTimeToLive: 'P7D'
    maxDeliveryCount: 10
  }
}

resource rootManageRule 'Microsoft.ServiceBus/namespaces/AuthorizationRules@2022-10-01-preview' existing = {
  parent: sbNamespace
  name: 'RootManageSharedAccessKey'
}

// Store Service Bus connection string in Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource sbConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'servicebus-connection-string'
  properties: { value: rootManageRule.listKeys().primaryConnectionString }
}

output id string = sbNamespace.id
output namespaceFqdn string = '${sbNamespace.name}.servicebus.windows.net'
output connectionSecretUri string = sbConnectionSecret.properties.secretUri
