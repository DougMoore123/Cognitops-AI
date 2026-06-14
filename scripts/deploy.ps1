<#
.SYNOPSIS
  CognitOps AI - Full Azure Deployment Script
  Provisions all Azure infrastructure via Bicep then seeds all 6 datasets.

.DESCRIPTION
  1. Sets azd environment variables
  2. Runs az deployment sub create (Bicep)
  3. Reads outputs and sets environment
  4. Copies CSVs to data/ directory
  5. Runs Python data ingestion pipeline

.PARAMETER EnvironmentName
  Azure environment name (default: cognitops-dev)

.PARAMETER Location
  Azure region (default: eastus)

.PARAMETER DataDir
  Path to CSV datasets (default: C:\Users\moore\Downloads\cognitops_ai_csv_datasets)
#>
param(
    [string]$EnvironmentName = "cognitops-dev",
    [string]$Location = "eastus",
    [string]$DataDir = "C:\Users\moore\Downloads\cognitops_ai_csv_datasets",
    [switch]$SkipInfra,
    [switch]$SkipIngestion
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " CognitOps AI - Azure Deployment" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Environment : $EnvironmentName"
Write-Host " Location    : $Location"
Write-Host " Data Dir    : $DataDir"
Write-Host ""

# ── Validate prerequisites ────────────────────────────────────────────────────
Write-Host "[0/5] Checking prerequisites..." -ForegroundColor Yellow

$principalId = (az ad signed-in-user show --query id -o tsv 2>$null)
if (-not $principalId) {
    Write-Error "Not logged in to Azure CLI. Run: az login"
}
$subscriptionId = (az account show --query id -o tsv)
Write-Host "  Subscription : $subscriptionId"
Write-Host "  Principal ID : $principalId"

# ── 1. Deploy Infrastructure ──────────────────────────────────────────────────
if (-not $SkipInfra) {
    Write-Host "`n[1/5] Deploying Azure infrastructure via Bicep..." -ForegroundColor Yellow

    $deploymentName = "cognitops-$EnvironmentName-$(Get-Date -Format 'yyyyMMddHHmm')"
    $bicepFile = Join-Path $ProjectRoot "infra\main.bicep"
    $paramsFile = Join-Path $ProjectRoot "infra\main.parameters.json"

    # Replace template vars in parameters
    $paramsContent = Get-Content $paramsFile -Raw
    $paramsContent = $paramsContent -replace '\$\{AZURE_ENV_NAME\}', $EnvironmentName
    $paramsContent = $paramsContent -replace '\$\{AZURE_LOCATION\}',  $Location
    $paramsContent = $paramsContent -replace '\$\{AZURE_PRINCIPAL_ID\}', $principalId
    $tempParams = [System.IO.Path]::GetTempFileName() + ".json"
    Set-Content $tempParams $paramsContent

    Write-Host "  Running: az deployment sub create..."
    az deployment sub create `
        --name $deploymentName `
        --location $Location `
        --template-file $bicepFile `
        --parameters $tempParams `
        --output json | Tee-Object -Variable deployOutput

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Bicep deployment failed. Check the output above."
    }
    Remove-Item $tempParams -Force

    Write-Host "  ✓ Infrastructure deployed!" -ForegroundColor Green
} else {
    Write-Host "`n[1/5] Skipping infrastructure deployment (--SkipInfra)" -ForegroundColor DarkGray
}

# ── 2. Read deployment outputs ────────────────────────────────────────────────
Write-Host "`n[2/5] Reading deployment outputs..." -ForegroundColor Yellow

$rgName = "rg-$EnvironmentName"

function Get-Output($name) {
    $val = (az deployment sub show --name "cognitops-$EnvironmentName*" --query "properties.outputs.$name.value" -o tsv 2>$null)
    if (-not $val) {
        # Try from resource group
        $val = (az deployment group list --resource-group $rgName --query "[0].properties.outputs.$name.value" -o tsv 2>$null)
    }
    return $val
}

# Fetch outputs from most recent deployment
$outputs = az deployment sub list `
    --query "[?starts_with(name,'cognitops-$EnvironmentName')].{name:name,state:properties.provisioningState}" `
    --output json | ConvertFrom-Json | Sort-Object name -Descending | Select-Object -First 1

if ($outputs) {
    $latestDeploy = $outputs.name
    Write-Host "  Reading outputs from deployment: $latestDeploy"

    $outputsJson = az deployment sub show --name $latestDeploy --query "properties.outputs" -o json | ConvertFrom-Json

    $env:AZURE_OPENAI_ENDPOINT          = $outputsJson.AZURE_OPENAI_ENDPOINT.value
    $env:AZURE_AI_SEARCH_ENDPOINT       = $outputsJson.AZURE_AI_SEARCH_ENDPOINT.value
    $env:AZURE_COSMOS_ENDPOINT          = $outputsJson.AZURE_COSMOS_ENDPOINT.value
    $env:AZURE_STORAGE_ACCOUNT_NAME     = $outputsJson.AZURE_STORAGE_ACCOUNT_NAME.value
    $env:AZURE_SERVICE_BUS_NAMESPACE    = $outputsJson.AZURE_SERVICE_BUS_NAMESPACE.value
    $env:AZURE_KEY_VAULT_ENDPOINT       = $outputsJson.AZURE_KEY_VAULT_ENDPOINT.value
    $env:AZURE_FOUNDRY_PROJECT_ENDPOINT = $outputsJson.AZURE_FOUNDRY_PROJECT_ENDPOINT.value
    $env:APPLICATIONINSIGHTS_CONNECTION_STRING = $outputsJson.APPLICATIONINSIGHTS_CONNECTION_STRING.value
    $env:AZURE_APIM_GATEWAY_URL         = $outputsJson.AZURE_APIM_GATEWAY_URL.value

    # Retrieve API keys from Key Vault
    $kvName = ($env:AZURE_KEY_VAULT_ENDPOINT -split '\.')[0] -replace 'https://',''
    $env:AZURE_OPENAI_API_KEY    = (az keyvault secret show --vault-name $kvName --name "openai-api-key"    --query value -o tsv 2>$null)
    $env:AZURE_AI_SEARCH_API_KEY = (az keyvault secret show --vault-name $kvName --name "search-admin-key"  --query value -o tsv 2>$null)

    Write-Host "  ✓ Outputs loaded" -ForegroundColor Green
    Write-Host "  OpenAI   : $($env:AZURE_OPENAI_ENDPOINT)"
    Write-Host "  Search   : $($env:AZURE_AI_SEARCH_ENDPOINT)"
    Write-Host "  Cosmos   : $($env:AZURE_COSMOS_ENDPOINT)"
    Write-Host "  APIM     : $($env:AZURE_APIM_GATEWAY_URL)"
} else {
    Write-Warning "No deployment found matching cognitops-$EnvironmentName. Set environment variables manually."
}

# ── 3. Write .env file for local development ──────────────────────────────────
Write-Host "`n[3/5] Writing .env file..." -ForegroundColor Yellow
$envFile = Join-Path $ProjectRoot ".env"
@"
# CognitOps AI - Generated environment variables
# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
AZURE_SUBSCRIPTION_ID=$subscriptionId
AZURE_RESOURCE_GROUP=$rgName
AZURE_OPENAI_ENDPOINT=$($env:AZURE_OPENAI_ENDPOINT)
AZURE_OPENAI_API_KEY=$($env:AZURE_OPENAI_API_KEY)
AZURE_OPENAI_DEPLOYMENT_GPT4O=gpt-4o
AZURE_OPENAI_DEPLOYMENT_EMBEDDING=text-embedding-3-large
AZURE_AI_SEARCH_ENDPOINT=$($env:AZURE_AI_SEARCH_ENDPOINT)
AZURE_AI_SEARCH_API_KEY=$($env:AZURE_AI_SEARCH_API_KEY)
AZURE_COSMOS_ENDPOINT=$($env:AZURE_COSMOS_ENDPOINT)
AZURE_STORAGE_ACCOUNT_NAME=$($env:AZURE_STORAGE_ACCOUNT_NAME)
AZURE_SERVICE_BUS_NAMESPACE=$($env:AZURE_SERVICE_BUS_NAMESPACE)
AZURE_KEY_VAULT_ENDPOINT=$($env:AZURE_KEY_VAULT_ENDPOINT)
AZURE_FOUNDRY_PROJECT_ENDPOINT=$($env:AZURE_FOUNDRY_PROJECT_ENDPOINT)
APPLICATIONINSIGHTS_CONNECTION_STRING=$($env:APPLICATIONINSIGHTS_CONNECTION_STRING)
AZURE_APIM_GATEWAY_URL=$($env:AZURE_APIM_GATEWAY_URL)
"@ | Set-Content $envFile
Write-Host "  ✓ .env written to $envFile" -ForegroundColor Green

# ── 4. Copy CSVs to scripts/data ──────────────────────────────────────────────
Write-Host "`n[4/5] Copying CSV datasets to scripts/data/..." -ForegroundColor Yellow
$scriptDataDir = Join-Path $ProjectRoot "scripts\data"
New-Item -ItemType Directory -Path $scriptDataDir -Force | Out-Null

$csvFiles = @("equipment_assets","maintenance_cases","sensor_readings","manual_index","parts_inventory","technician_feedback")
foreach ($f in $csvFiles) {
    $src = Join-Path $DataDir "$f.csv"
    $dst = Join-Path $scriptDataDir "$f.csv"
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "  Copied: $f.csv"
    } else {
        Write-Warning "  Not found: $src"
    }
}

# ── 5. Run data ingestion pipeline ────────────────────────────────────────────
if (-not $SkipIngestion) {
    Write-Host "`n[5/5] Running data ingestion pipeline..." -ForegroundColor Yellow

    # Check Python
    $python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if (-not $python) { $python = "python3" }

    Push-Location (Join-Path $ProjectRoot "scripts")
    try {
        Write-Host "  Installing ingestion dependencies..."
        & $python -m pip install -r requirements.txt --quiet

        Write-Host "  Running ingest_data.py..."
        & $python ingest_data.py --data-dir data

        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ Data ingestion complete!" -ForegroundColor Green
        } else {
            Write-Warning "  Data ingestion exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n[5/5] Skipping data ingestion (--SkipIngestion)" -ForegroundColor DarkGray
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host " CognitOps AI Deployment Complete!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Resource Group : $rgName"
Write-Host " APIM Gateway   : $($env:AZURE_APIM_GATEWAY_URL)"
Write-Host " Key Vault      : $($env:AZURE_KEY_VAULT_ENDPOINT)"
Write-Host ""
Write-Host " API Endpoints:"
Write-Host "   POST $($env:AZURE_APIM_GATEWAY_URL)/api/diagnostics/cases   (submit case)"
Write-Host "   GET  $($env:AZURE_APIM_GATEWAY_URL)/api/supervisor/queue     (review queue)"
Write-Host ""
Write-Host " Next steps:"
Write-Host "   1. Build & push container images:"
Write-Host "      az acr build --registry <acr> --image cognitops/orchestrator:latest src/orchestrator"
Write-Host "   2. Update Container App images in Azure Portal or via az containerapp update"
Write-Host "   3. Open Azure Foundry project at: https://ai.azure.com"
Write-Host ""
