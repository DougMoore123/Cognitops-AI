param location string
param tags object
param name string
param applicationInsightsId string
param applicationInsightsInstrumentationKey string
param orchestratorUrl string
param supervisorApiUrl string

resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'Consumption', capacity: 0 }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: 'admin@cognitops.ai'
    publisherName: 'CognitOps AI'
    customProperties: {
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Tls10': 'false'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Tls11': 'false'
    }
  }
}

// App Insights logger
resource apimLogger 'Microsoft.ApiManagement/service/loggers@2023-09-01-preview' = {
  parent: apim
  name: 'cognitops-logger'
  properties: {
    loggerType: 'applicationInsights'
    credentials: { instrumentationKey: applicationInsightsInstrumentationKey }
    isBuffered: true
    resourceId: applicationInsightsId
  }
}

// API diagnostic
resource apimDiagnostic 'Microsoft.ApiManagement/service/diagnostics@2023-09-01-preview' = {
  parent: apim
  name: 'applicationinsights'
  properties: {
    alwaysLog: 'allErrors'
    httpCorrelationProtocol: 'W3C'
    loggerId: apimLogger.id
    logClientIp: true
    sampling: { samplingType: 'fixed', percentage: 100 }
    frontend: {
      request: { headers: [], body: { bytes: 1024 } }
      response: { headers: [], body: { bytes: 1024 } }
    }
    backend: {
      request: { headers: [], body: { bytes: 1024 } }
      response: { headers: [], body: { bytes: 1024 } }
    }
  }
}

// Named values for backend URLs
resource orchestratorNv 'Microsoft.ApiManagement/service/namedValues@2023-09-01-preview' = {
  parent: apim
  name: 'orchestrator-url'
  properties: { displayName: 'orchestrator-url', value: orchestratorUrl, secret: false }
}

resource supervisorNv 'Microsoft.ApiManagement/service/namedValues@2023-09-01-preview' = {
  parent: apim
  name: 'supervisor-api-url'
  properties: { displayName: 'supervisor-api-url', value: supervisorApiUrl, secret: false }
}

// ── CognitOps API Product ────────────────────────────────────────────────────
resource product 'Microsoft.ApiManagement/service/products@2023-09-01-preview' = {
  parent: apim
  name: 'cognitops'
  properties: {
    displayName: 'CognitOps AI'
    description: 'Field Service Intelligence Platform APIs'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

// ── Field Diagnostics API ────────────────────────────────────────────────────
resource diagnosticsApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = {
  parent: apim
  name: 'field-diagnostics'
  properties: {
    displayName: 'Field Diagnostics API'
    description: 'Submit equipment images and issue descriptions for AI diagnosis'
    path: 'api/diagnostics'
    protocols: ['https']
    subscriptionRequired: true
    apiType: 'http'
    serviceUrl: orchestratorUrl
  }
}

resource submitCaseOp 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: diagnosticsApi
  name: 'submit-case'
  properties: {
    displayName: 'Submit Diagnostic Case'
    method: 'POST'
    urlTemplate: '/cases'
    description: 'Submit a multimodal equipment case (image + description) for AI diagnosis'
    request: {
      description: 'Multipart form data with image and issue description'
      representations: [{ contentType: 'multipart/form-data' }]
    }
    responses: [{
      statusCode: 200
      description: 'AI diagnosis result with severity score and recommendations'
      representations: [{ contentType: 'application/json' }]
    }]
  }
}

resource getCaseOp 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: diagnosticsApi
  name: 'get-case'
  properties: {
    displayName: 'Get Diagnostic Case'
    method: 'GET'
    urlTemplate: '/cases/{caseId}'
    templateParameters: [{ name: 'caseId', required: true, type: 'string' }]
    description: 'Retrieve a diagnostic case by ID'
    responses: [{ statusCode: 200, description: 'Case details' }]
  }
}

// Rate limiting and auth policy on the diagnostics API
resource diagnosticsApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-09-01-preview' = {
  parent: diagnosticsApi
  name: 'policy'
  properties: {
    format: 'xml'
    value: '''<policies>
  <inbound>
    <base />
    <rate-limit calls="30" renewal-period="60" />
    <quota calls="5000" renewal-period="86400" />
    <set-header name="X-Request-ID" exists-action="skip">
      <value>@(context.RequestId.ToString())</value>
    </set-header>
    <set-header name="X-CognitOps-Version" exists-action="override">
      <value>1.0</value>
    </set-header>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
    <set-header name="X-Powered-By" exists-action="delete" />
    <set-header name="Server" exists-action="delete" />
  </outbound>
  <on-error>
    <base />
    <return-response>
      <set-status code="@(context.Response.StatusCode)" reason="@(context.Response.StatusReason)" />
      <set-header name="Content-Type" exists-action="override">
        <value>application/json</value>
      </set-header>
      <set-body>@(new JObject(new JProperty("error", context.LastError.Message), new JProperty("requestId", context.RequestId)).ToString())</set-body>
    </return-response>
  </on-error>
</policies>'''
  }
}

// ── Supervisor Review API ────────────────────────────────────────────────────
resource supervisorApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = {
  parent: apim
  name: 'supervisor-review'
  properties: {
    displayName: 'Supervisor Review API'
    description: 'Human-in-the-loop review queue for escalated cases'
    path: 'api/supervisor'
    protocols: ['https']
    subscriptionRequired: true
    apiType: 'http'
    serviceUrl: supervisorApiUrl
  }
}

resource getQueueOp 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: supervisorApi
  name: 'get-queue'
  properties: {
    displayName: 'Get Escalation Queue'
    method: 'GET'
    urlTemplate: '/queue'
    description: 'Get all pending cases awaiting supervisor review'
  }
}

resource approveCaseOp 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: supervisorApi
  name: 'approve-case'
  properties: {
    displayName: 'Approve Escalated Case'
    method: 'POST'
    urlTemplate: '/queue/{caseId}/approve'
    templateParameters: [{ name: 'caseId', required: true, type: 'string' }]
    description: 'Supervisor approves AI recommendation and releases to technician'
  }
}

resource rejectCaseOp 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: supervisorApi
  name: 'reject-case'
  properties: {
    displayName: 'Reject / Redirect Case'
    method: 'POST'
    urlTemplate: '/queue/{caseId}/reject'
    templateParameters: [{ name: 'caseId', required: true, type: 'string' }]
    description: 'Supervisor rejects AI recommendation with override notes'
  }
}

// Associate APIs to product
resource diagnosticsProductLink 'Microsoft.ApiManagement/service/products/apis@2023-09-01-preview' = {
  parent: product
  name: 'field-diagnostics'
  dependsOn: [diagnosticsApi]
}

resource supervisorProductLink 'Microsoft.ApiManagement/service/products/apis@2023-09-01-preview' = {
  parent: product
  name: 'supervisor-review'
  dependsOn: [supervisorApi]
}

output id string = apim.id
output name string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
output principalId string = apim.identity.principalId
