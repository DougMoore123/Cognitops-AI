param location string
param tags object
param name string
param logAnalyticsWorkspaceId string
param acrId string

resource aks 'Microsoft.ContainerService/managedClusters@2024-02-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dnsPrefix: name
    kubernetesVersion: '1.30'
    enableRBAC: true

    oidcIssuerProfile: {
      enabled: true
    }
    securityProfile: {
      workloadIdentity: {
        enabled: true
      }
    }

    agentPoolProfiles: [
      {
        name: 'system'
        count: 2
        vmSize: 'Standard_D2s_v3'
        osType: 'Linux'
        mode: 'System'
        enableAutoScaling: true
        minCount: 2
        maxCount: 5
        nodeTaints: []
      }
      {
        name: 'workload'
        count: 2
        vmSize: 'Standard_D4s_v3'
        osType: 'Linux'
        mode: 'User'
        enableAutoScaling: true
        minCount: 2
        maxCount: 10
      }
    ]

    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      networkPolicy: 'azure'
      loadBalancerSku: 'standard'
    }

    addonProfiles: {
      azureKeyvaultSecretsProvider: {
        enabled: true
        config: {
          enableSecretRotation: 'true'
          rotationPollInterval: '2m'
        }
      }
      omsagent: {
        enabled: true
        config: {
          logAnalyticsWorkspaceResourceID: logAnalyticsWorkspaceId
        }
      }
    }
  }
}

// Grant AKS kubelet identity the AcrPull role on the container registry
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aks.id, acrId, 'acrpull')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

output id string = aks.id
output name string = aks.name
output oidcIssuerUrl string = aks.properties.oidcIssuerProfile.issuerURL
output kubeletPrincipalId string = aks.properties.identityProfile.kubeletidentity.objectId
output fqdn string = aks.properties.fqdn
