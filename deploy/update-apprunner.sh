#!/bin/bash
# Update existing App Runner service to use our new ECR image.
# This avoids iam:PassRole since the service already has roles attached.
#
# Includes MCP Adapter configuration env vars.
# To enable MCP routing, set USE_MCP_ADAPTER=true before running.

set -euo pipefail

PROFILE="PowerUserAccess-654654478821"
REGION="us-east-1"
ACCOUNT_ID="654654478821"
SSL="--no-verify-ssl"

SERVICE_ARN="arn:aws:apprunner:us-east-1:654654478821:service/conversational-bi-prod/707ab1e1b4c8486f92c877b68444c21d"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/conversational-bi-prod:latest"

# MCP Adapter Feature Flags
USE_MCP_ADAPTER="${USE_MCP_ADAPTER:-false}"
USE_MCP_REDSHIFT="${USE_MCP_REDSHIFT:-false}"
USE_MCP_S3="${USE_MCP_S3:-false}"

# MCP Server Configuration
MCP_ADAPTER_REDSHIFT_TRANSPORT="${MCP_ADAPTER_REDSHIFT_TRANSPORT:-stdio}"
MCP_ADAPTER_REDSHIFT_COMMAND="${MCP_ADAPTER_REDSHIFT_COMMAND:-}"
MCP_ADAPTER_REDSHIFT_TIMEOUT="${MCP_ADAPTER_REDSHIFT_TIMEOUT:-30}"
MCP_ADAPTER_S3_TRANSPORT="${MCP_ADAPTER_S3_TRANSPORT:-stdio}"
MCP_ADAPTER_S3_COMMAND="${MCP_ADAPTER_S3_COMMAND:-}"
MCP_ADAPTER_S3_TIMEOUT="${MCP_ADAPTER_S3_TIMEOUT:-30}"

echo "→ Updating App Runner service environment variables..."
echo "  Service: talk2data-ui"
echo "  MCP Mode: $([ "$USE_MCP_ADAPTER" = "true" ] && echo "ENABLED" || echo "disabled")"
echo ""

# Update only the image configuration (env vars) — do NOT re-specify
# AuthenticationConfiguration to avoid iam:PassRole requirement.
aws apprunner update-service \
  --service-arn "$SERVICE_ARN" \
  --source-configuration "{
    \"ImageRepository\": {
      \"ImageIdentifier\": \"${ECR_URI}\",
      \"ImageRepositoryType\": \"ECR\",
      \"ImageConfiguration\": {
        \"Port\": \"8001\",
        \"RuntimeEnvironmentVariables\": {
          \"AWS_REGION\": \"us-east-1\",
          \"S3_BUCKET\": \"visualization-poc-bucket\",
          \"GUARDRAIL_ID\": \"unf4323uxnff\",
          \"ENVIRONMENT\": \"prod\",
          \"USE_MCP_ADAPTER\": \"${USE_MCP_ADAPTER}\",
          \"USE_MCP_REDSHIFT\": \"${USE_MCP_REDSHIFT}\",
          \"USE_MCP_S3\": \"${USE_MCP_S3}\",
          \"MCP_ADAPTER_REDSHIFT_TRANSPORT\": \"${MCP_ADAPTER_REDSHIFT_TRANSPORT}\",
          \"MCP_ADAPTER_REDSHIFT_COMMAND\": \"${MCP_ADAPTER_REDSHIFT_COMMAND}\",
          \"MCP_ADAPTER_REDSHIFT_TIMEOUT\": \"${MCP_ADAPTER_REDSHIFT_TIMEOUT}\",
          \"MCP_ADAPTER_S3_TRANSPORT\": \"${MCP_ADAPTER_S3_TRANSPORT}\",
          \"MCP_ADAPTER_S3_COMMAND\": \"${MCP_ADAPTER_S3_COMMAND}\",
          \"MCP_ADAPTER_S3_TIMEOUT\": \"${MCP_ADAPTER_S3_TIMEOUT}\"
        }
      }
    }
  }" \
  --profile "$PROFILE" --region "$REGION" $SSL \
  --query "Service.{Status:Status,URL:ServiceUrl}" --output text

echo ""
echo "✓ Update triggered!"
echo "  URL: https://jwxrxfzsjr.us-east-1.awsapprunner.com"
echo "  The service will redeploy in 2-3 minutes."
echo "  Check health: curl https://jwxrxfzsjr.us-east-1.awsapprunner.com/health"
echo ""
echo "  To enable MCP routing on next deploy:"
echo "    USE_MCP_ADAPTER=true USE_MCP_REDSHIFT=true USE_MCP_S3=true bash deploy/update-apprunner.sh"
