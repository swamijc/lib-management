#!/usr/bin/env bash
# =============================================================================
#  deploy/azure/deploy.sh — Full Azure deployment for SDK Management App
#  Usage: bash deploy/azure/deploy.sh
# =============================================================================
set -euo pipefail

# ── Config (edit these if you want different names) ───────────────────────────
RESOURCE_GROUP="sdk-management-rg"
LOCATION="eastus"
ACR_NAME="sdkmgmtacr$(openssl rand -hex 3)"   # must be globally unique
CONTAINER_APP_ENV="sdk-mgmt-env"
BACKEND_APP="sdk-mgmt-backend"
FRONTEND_APP="sdk-mgmt-frontend"
IMAGE_TAG="latest"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
info()    { echo -e "${CYAN}  →${RESET} $*"; }
ok()      { echo -e "${GREEN}  ✓${RESET} $*"; }
section() { echo -e "\n${BOLD}$*${RESET}"; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
section "Pre-flight checks"
command -v az >/dev/null || { echo "${RED}Azure CLI not found. Install with: brew install azure-cli${RESET}"; exit 1; }
ok "Azure CLI found"

# Persist names for later reference
STATE_FILE="$SCRIPT_DIR/.deploy-state"

# ── Resource Group ─────────────────────────────────────────────────────────────
section "1/7  Resource Group"
if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
  info "Resource group '$RESOURCE_GROUP' already exists"
else
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
  ok "Created resource group '$RESOURCE_GROUP' in $LOCATION"
fi

# ── Azure Container Registry ───────────────────────────────────────────────────
section "2/7  Azure Container Registry"
# Reuse ACR name if previously deployed
if [[ -f "$STATE_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$STATE_FILE"
fi

if [[ -z "${ACR_NAME:-}" ]] || ! az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
  ACR_NAME="sdkmgmtacr$(openssl rand -hex 3)"
  az acr create \
    --name "$ACR_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku Basic \
    --admin-enabled true \
    --output none
  ok "Created ACR: $ACR_NAME"
else
  info "Reusing ACR: $ACR_NAME"
fi

ACR_SERVER=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)
IMAGE_FULL="$ACR_SERVER/$BACKEND_APP:$IMAGE_TAG"

# Persist state
cat > "$STATE_FILE" <<EOF
ACR_NAME="$ACR_NAME"
ACR_SERVER="$ACR_SERVER"
BACKEND_APP="$BACKEND_APP"
FRONTEND_APP="$FRONTEND_APP"
CONTAINER_APP_ENV="$CONTAINER_APP_ENV"
RESOURCE_GROUP="$RESOURCE_GROUP"
EOF

# ── Build & Push Docker image (cloud build — no local Docker needed) ──────────
section "3/7  Build & Push Docker image (cloud build)"
info "Uploading source and building in ACR (this takes ~5-8 minutes)..."

cd "$APP_ROOT"
az acr build \
  --registry "$ACR_NAME" \
  --image "$BACKEND_APP:$IMAGE_TAG" \
  --file deploy/azure/Dockerfile \
  .
ok "Image built and pushed: $IMAGE_FULL"

# ── Container Apps Environment ─────────────────────────────────────────────────
section "4/7  Container Apps Environment"
az extension add --name containerapp --upgrade --output none 2>/dev/null || true
az provider register --namespace Microsoft.App --output none 2>/dev/null || true
az provider register --namespace Microsoft.OperationalInsights --output none 2>/dev/null || true

if az containerapp env show --name "$CONTAINER_APP_ENV" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
  info "Environment '$CONTAINER_APP_ENV' already exists"
else
  info "Creating Container Apps environment..."
  az containerapp env create \
    --name "$CONTAINER_APP_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
  ok "Created environment: $CONTAINER_APP_ENV"
fi

# ── Backend Container App ──────────────────────────────────────────────────────
section "5/7  Backend Container App"

# Read secrets from .env file
ENV_FILE="$APP_ROOT/.env"
JWT_SECRET="$(grep JWT_SECRET_KEY "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo 'change-in-prod')"
INTERNAL_KEY="$(grep INTERNAL_SERVICE_KEY "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo 'change-in-prod')"
ADMIN_PW="$(grep DEFAULT_ADMIN_PASSWORD "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo 'admin123')"
LLM_KEY="$(grep LLM_KEY "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo '')"

if az containerapp show --name "$BACKEND_APP" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
  info "Updating existing backend app..."
  az containerapp update \
    --name "$BACKEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$IMAGE_FULL" \
    --output none
else
  info "Creating backend Container App..."
  az containerapp create \
    --name "$BACKEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINER_APP_ENV" \
    --image "$IMAGE_FULL" \
    --registry-server "$ACR_SERVER" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 8000 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 2 \
    --memory 4Gi \
    --env-vars \
      "DATABASE_URL=sqlite+aiosqlite:////data/db/library_management.db" \
      "JWT_SECRET_KEY=$JWT_SECRET" \
      "INTERNAL_SERVICE_KEY=$INTERNAL_KEY" \
      "DEFAULT_ADMIN_PASSWORD=$ADMIN_PW" \
      "LLM_API_KEY=$LLM_KEY" \
      "LLM_PROVIDER=openai" \
      "LLM_MODEL=gpt-4o-mini" \
      "SCHEDULE_ENABLED=true" \
    --output none
fi

BACKEND_URL=$(az containerapp show \
  --name "$BACKEND_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)
BACKEND_URL="https://$BACKEND_URL"
ok "Backend deployed: $BACKEND_URL"

# ── React Frontend — build ────────────────────────────────────────────────────
section "6/7  React Frontend (Azure Static Web Apps)"
REACT_DIR="$APP_ROOT/services/ui-react"

info "Building React app..."
cd "$REACT_DIR"

# Write production env with cloud backend URL
cat > .env.production <<EOF
VITE_API_BASE_URL=$BACKEND_URL
EOF

npm install --silent
VITE_API_BASE_URL="$BACKEND_URL" npm run build --silent
ok "React build complete (dist/)"

# Deploy via Azure Static Web Apps CLI
info "Deploying to Azure Static Web Apps..."
# Install SWA CLI if needed
command -v swa >/dev/null 2>&1 || npm install -g @azure/static-web-apps-cli --silent

# Create Static Web App resource
if ! az staticwebapp show --name "$FRONTEND_APP" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
  az staticwebapp create \
    --name "$FRONTEND_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --location "eastus2" \
    --sku Free \
    --output none
  ok "Created Static Web App: $FRONTEND_APP"
fi

DEPLOY_TOKEN=$(az staticwebapp secrets list \
  --name "$FRONTEND_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.apiKey" -o tsv)

swa deploy dist/ \
  --deployment-token "$DEPLOY_TOKEN" \
  --env production \
  --no-use-keychain 2>&1 | grep -E "Deploying|Deployment|URL|✓|Error" || true

FRONTEND_URL=$(az staticwebapp show \
  --name "$FRONTEND_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query "defaultHostname" -o tsv)

ok "Frontend deployed: https://$FRONTEND_URL"

# ── Summary ────────────────────────────────────────────────────────────────────
section "7/7  Deployment Complete"
echo ""
echo -e "  ${GREEN}${BOLD}✓ Backend API${RESET}  : $BACKEND_URL"
echo -e "  ${GREEN}${BOLD}✓ Frontend UI${RESET}  : https://$FRONTEND_URL"
echo -e "  ${GREEN}${BOLD}✓ API Docs${RESET}     : $BACKEND_URL/docs"
echo ""
echo -e "  Login: ${BOLD}admin${RESET} / ${BOLD}$ADMIN_PW${RESET}"
echo ""

# Append to state file
cat >> "$STATE_FILE" <<EOF
BACKEND_URL="$BACKEND_URL"
FRONTEND_URL="https://$FRONTEND_URL"
EOF
