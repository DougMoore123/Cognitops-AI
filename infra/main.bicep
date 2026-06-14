targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (used for resource naming)')
param environmentName string

@minLength(1)
@description('Primary Azure region for all resources')
param location string = 'eastus'

@description('Object ID of the principal to assign roles (leave empty to skip role assignments)')
param principalId string = ''

// ── Naming ──────────────────────────────────────────────────────────────────
var abbrs = loadJsonContent('abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName, project: 'cognitops-ai' }

// ── Resource Group ───────────────────────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// ── Monitoring (Log Analytics + App Insights) ────────────────────────────────
module monitoring 'core/monitoring/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
  }
}

// ── Key Vault ────────────────────────────────────────────────────────────────
module keyVault 'core/security/keyvault.bicep' = {
  name: 'keyvault'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.keyVaultVaults}${resourceToken}'
    principalId: principalId
  }
}

// ── Storage Account ──────────────────────────────────────────────────────────
module storage 'core/storage/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    keyVaultName: keyVault.outputs.name
  }
}

// ── Azure AI Search ──────────────────────────────────────────────────────────
module aiSearch 'core/ai/search.bicep' = {
  name: 'ai-search'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.searchSearchServices}${resourceToken}'
    keyVaultName: keyVault.outputs.name
    principalId: principalId
  }
}

// ── Azure OpenAI ─────────────────────────────────────────────────────────────
module openAI 'core/ai/openai.bicep' = {
  name: 'openai'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.cognitiveServicesAccounts}oai-${resourceToken}'
    keyVaultName: keyVault.outputs.name
    principalId: principalId
  }
}

// ── Azure AI Foundry Hub + Project ────────────────────────────────────────────
module foundryHub 'core/ai/foundry-hub.bicep' = {
  name: 'foundry-hub'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.machineLearningWorkspaces}hub-${resourceToken}'
    storageAccountId: storage.outputs.id
    keyVaultId: keyVault.outputs.id
    applicationInsightsId: monitoring.outputs.applicationInsightsId
    openAiServiceId: openAI.outputs.id
    searchServiceId: aiSearch.outputs.id
  }
}

module foundryProject 'core/ai/foundry-project.bicep' = {
  name: 'foundry-project'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.machineLearningWorkspaces}proj-${resourceToken}'
    hubName: foundryHub.outputs.name
  }
}

// ── Cosmos DB ────────────────────────────────────────────────────────────────
module cosmosDb 'core/storage/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    location: location
    tags: tags
    accountName: '${abbrs.documentDBDatabaseAccounts}${resourceToken}'
    keyVaultName: keyVault.outputs.name
    principalId: principalId
  }
}

// ── Service Bus ──────────────────────────────────────────────────────────────
module serviceBus 'core/messaging/servicebus.bicep' = {
  name: 'servicebus'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.serviceBusNamespaces}${resourceToken}'
    keyVaultName: keyVault.outputs.name
  }
}

// ── Container Apps Environment ───────────────────────────────────────────────
module containerAppsEnv 'core/compute/container-apps-env.bicep' = {
  name: 'container-apps-env'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    logAnalyticsWorkspaceCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsWorkspaceKey: monitoring.outputs.logAnalyticsPrimaryKey
  }
}

// ── Container Apps (microservices) ───────────────────────────────────────────
module containerApps 'core/compute/container-apps.bicep' = {
  name: 'container-apps'
  scope: rg
  params: {
    location: location
    tags: tags
    environmentId: containerAppsEnv.outputs.id
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    openAiEndpoint: openAI.outputs.endpoint
    openAiKeySecretUri: openAI.outputs.keySecretUri
    searchEndpoint: aiSearch.outputs.endpoint
    searchKeySecretUri: aiSearch.outputs.keySecretUri
    cosmosEndpoint: cosmosDb.outputs.endpoint
    cosmosKeySecretUri: cosmosDb.outputs.keySecretUri
    serviceBusNamespace: serviceBus.outputs.namespaceFqdn
    serviceBusConnectionSecretUri: serviceBus.outputs.connectionSecretUri
    storageAccountName: storage.outputs.name
    storageKeySecretUri: storage.outputs.keySecretUri
    keyVaultName: keyVault.outputs.name
    foundryProjectEndpoint: foundryProject.outputs.endpoint
  }
}

// ── API Management ────────────────────────────────────────────────────────────
module apim 'core/gateway/apim.bicep' = {
  name: 'apim'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.apiManagementService}${resourceToken}'
    applicationInsightsId: monitoring.outputs.applicationInsightsId
    applicationInsightsInstrumentationKey: monitoring.outputs.applicationInsightsInstrumentationKey
    orchestratorUrl: containerApps.outputs.orchestratorUrl
    supervisorApiUrl: containerApps.outputs.supervisorApiUrl
  }
}

// ── Azure Container Registry ──────────────────────────────────────────────────
module acr 'core/compute/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.containerRegistries}${resourceToken}'
    keyVaultName: keyVault.outputs.name
  }
}

// ── AKS Cluster ───────────────────────────────────────────────────────────────
module aks 'core/compute/aks.bicep' = {
  name: 'aks'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.managedClusters}${resourceToken}'
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    acrId: acr.outputs.id
  }
}

// ── Azure Machine Learning (MLflow tracking) ──────────────────────────────────
module amlWorkspace 'core/ai/azureml.bicep' = {
  name: 'aml'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.mlWorkspaces}${resourceToken}'
    storageAccountId: storage.outputs.id
    keyVaultId: keyVault.outputs.id
    applicationInsightsId: monitoring.outputs.applicationInsightsId
    principalId: principalId
  }
}

// ── Static Web App (React frontend) ──────────────────────────────────────────
module staticWebApp 'core/host/staticwebapp.bicep' = {
  name: 'staticwebapp'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.staticSites}${resourceToken}'
    keyVaultName: keyVault.outputs.name
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name

output AZURE_OPENAI_ENDPOINT string = openAI.outputs.endpoint
output AZURE_OPENAI_DEPLOYMENT_GPT4O string = openAI.outputs.gpt4oDeploymentName
output AZURE_OPENAI_DEPLOYMENT_EMBEDDING string = openAI.outputs.embeddingDeploymentName

output AZURE_AI_SEARCH_ENDPOINT string = aiSearch.outputs.endpoint
output AZURE_FOUNDRY_PROJECT_ENDPOINT string = foundryProject.outputs.endpoint
output AZURE_COSMOS_ENDPOINT string = cosmosDb.outputs.endpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.name
output AZURE_SERVICE_BUS_NAMESPACE string = serviceBus.outputs.namespaceFqdn
output AZURE_KEY_VAULT_ENDPOINT string = keyVault.outputs.endpoint
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.applicationInsightsConnectionString
output AZURE_APIM_GATEWAY_URL string = apim.outputs.gatewayUrl
output AZURE_ACR_LOGIN_SERVER string = acr.outputs.loginServer
output AZURE_ACR_NAME string = acr.outputs.name
output AZURE_AKS_NAME string = aks.outputs.name
output AZURE_AKS_OIDC_ISSUER string = aks.outputs.oidcIssuerUrl
output AZURE_AML_WORKSPACE_NAME string = amlWorkspace.outputs.name
output AZURE_MLFLOW_TRACKING_URI string = amlWorkspace.outputs.mlflowTrackingUri
output AZURE_STATIC_WEB_APP_HOSTNAME string = staticWebApp.outputs.defaultHostname
