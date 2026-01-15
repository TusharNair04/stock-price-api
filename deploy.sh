#!/bin/bash
set -e

# Configuration
AWS_REGION="${AWS_REGION:-eu-central-1}"
STACK_NAME="stock-price-api"
API_KEY="${API_KEY:-}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Check for SAM CLI
if ! command -v sam &> /dev/null; then
    echo -e "${RED}Error: SAM CLI is not installed${NC}"
    echo "Install with: brew install aws-sam-cli (macOS) or pip install aws-sam-cli"
    exit 1
fi

# Get AWS account info
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}Error: Not authenticated with AWS. Run 'aws configure' or set credentials${NC}"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Stock Price API - AWS Lambda Deploy${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Account:  ${YELLOW}${AWS_ACCOUNT_ID}${NC}"
echo -e "Region:   ${YELLOW}${AWS_REGION}${NC}"
echo -e "Stack:    ${YELLOW}${STACK_NAME}${NC}"
echo ""

# Prompt for API key if not set
if [ -z "$API_KEY" ]; then
    echo -e "${YELLOW}API Key not set. The API will require authentication.${NC}"
    read -p "Enter API key (or press Enter to generate one): " API_KEY
    if [ -z "$API_KEY" ]; then
        API_KEY=$(openssl rand -hex 16)
        echo -e "Generated API key: ${YELLOW}${API_KEY}${NC}"
    fi
fi

echo -e "API Key:  ${YELLOW}${API_KEY:0:8}...${NC} (masked)"
echo ""

# Confirm deployment
read -p "Proceed with deployment? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo -e "${GREEN}Building container image...${NC}"
echo ""

# Build with SAM
sam build --use-container

echo ""
echo -e "${GREEN}Deploying to AWS Lambda...${NC}"
echo ""

# Build parameter overrides
PARAM_OVERRIDES="ApiKey=${API_KEY}"
if [ -n "$GEMINI_API_KEY" ]; then
    PARAM_OVERRIDES="${PARAM_OVERRIDES} GeminiApiKey=${GEMINI_API_KEY}"
fi

# Deploy with SAM
sam deploy \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --resolve-s3 \
    --resolve-image-repos \
    --capabilities CAPABILITY_IAM \
    --no-confirm-changeset \
    --parameter-overrides "${PARAM_OVERRIDES}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Get API endpoint
API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -n "$API_ENDPOINT" ]; then
    echo -e "API Endpoint: ${YELLOW}${API_ENDPOINT}${NC}"
    echo -e "API Docs:     ${YELLOW}${API_ENDPOINT}/docs${NC}"
    echo -e "Health Check: ${YELLOW}${API_ENDPOINT}/health${NC}"
    echo ""
    echo -e "${GREEN}Authentication:${NC}"
    echo -e "API Key:      ${YELLOW}${API_KEY}${NC}"
    echo ""
    echo -e "Example request:"
    echo -e "  curl -X POST ${API_ENDPOINT}/quote \\"
    echo -e "    -H 'Content-Type: application/json' \\"
    echo -e "    -H 'X-API-Key: ${API_KEY}' \\"
    echo -e "    -d '{\"ticker\":\"AAPL\"}'"
fi
