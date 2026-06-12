#!/bin/bash
# Update existing App Runner service to use our new ECR image.
# This avoids iam:PassRole since the service already has roles attached.

set -euo pipefail

PROFILE="PowerUserAccess-654654478821"
REGION="us-east-1"
ACCOUNT_ID="654654478821"
SSL="--no-verify-ssl"

SERVICE_ARN="arn:aws:apprunner:us-east-1:654654478821:service/talk2data-ui/fffa39f37174487fa78d4de515d79195"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/conversational-bi-prod:latest"

echo "→ Updating App Runner service to use new image..."
echo "  Service: talk2data-ui"
echo "  New image: $ECR_URI"
echo ""

aws apprunner update-service \
  --service-arn "$SERVICE_ARN" \
  --source-configuration "{
    \"AuthenticationConfiguration\": {
      \"AccessRoleArn\": \"arn:aws:iam::${ACCOUNT_ID}:role/AppRunnerECRAccessRole\"
    },
    \"AutoDeploymentsEnabled\": true,
    \"ImageRepository\": {
      \"ImageIdentifier\": \"${ECR_URI}\",
      \"ImageRepositoryType\": \"ECR\",
      \"ImageConfiguration\": {
        \"Port\": \"8001\",
        \"RuntimeEnvironmentVariables\": {
          \"AWS_REGION\": \"us-east-1\",
          \"S3_BUCKET\": \"visualization-poc-bucket\",
          \"GUARDRAIL_ID\": \"joes1p3j7sa4\",
          \"ENVIRONMENT\": \"prod\"
        }
      }
    }
  }" \
  --profile "$PROFILE" --region "$REGION" $SSL \
  --query "Service.{Status:Status,URL:ServiceUrl}" --output text

echo ""
echo "✓ Update triggered!"
echo "  URL: https://pcacjyfkiz.us-east-1.awsapprunner.com"
echo "  The service will redeploy in 2-3 minutes."
echo "  Check health: curl https://pcacjyfkiz.us-east-1.awsapprunner.com/health"
