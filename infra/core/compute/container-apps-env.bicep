param location string
param tags object
param name string
param logAnalyticsWorkspaceCustomerId string
@secure()
param logAnalyticsWorkspaceKey string

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    daprAIInstrumentationKey: ''
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspaceCustomerId
        sharedKey: logAnalyticsWorkspaceKey
      }
    }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
  }
}

output id string = containerAppsEnv.id
output name string = containerAppsEnv.name
output defaultDomain string = containerAppsEnv.properties.defaultDomain
