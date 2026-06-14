param location string
param tags object
param name string
param hubName string

resource foundryHub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' existing = {
  name: hubName
}

resource foundryProject 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'Project'
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Basic', tier: 'Basic' }
  properties: {
    friendlyName: 'CognitOps AI Project'
    description: 'CognitOps AI agent project for field service intelligence'
    hubResourceId: foundryHub.id
    publicNetworkAccess: 'Enabled'
  }
}

output id string = foundryProject.id
output name string = foundryProject.name
output principalId string = foundryProject.identity.principalId
// Foundry project endpoint format
output endpoint string = 'https://${location}.api.azureml.ms/raisvc/v1.0/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.MachineLearningServices/workspaces/${foundryProject.name}'
