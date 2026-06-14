param location string
param tags object
param name string
param storageAccountId string
param keyVaultId string
param applicationInsightsId string
param principalId string

resource amlWorkspace 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: name
    storageAccount: storageAccountId
    keyVault: keyVaultId
    applicationInsights: applicationInsightsId
    publicNetworkAccess: 'Enabled'
  }
}

// Grant the deploying principal access to submit experiments / read MLflow tracking
resource mlDataScientist 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(amlWorkspace.id, principalId, 'aml-data-scientist')
  scope: amlWorkspace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f6c7c914-8db3-469d-8ca1-694a8f32e121') // AzureML Data Scientist
    principalId: principalId
    principalType: 'User'
  }
}

output id string = amlWorkspace.id
output name string = amlWorkspace.name
// MLflow tracking URI — used by Python services and the diagnostic engine
output mlflowTrackingUri string = 'azureml://eastus.api.azureml.ms/mlflow/v1.0/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.MachineLearningServices/workspaces/${amlWorkspace.name}'
