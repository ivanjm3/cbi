#!/bin/bash
# Creates App Runner service after ECR has an image.
# Run this after the first CodeBuild completes successfully.

set -euo pipefail

PROFILE="PowerUserAccess-654654478821"
REGION="us-east-1"
ACCOUNT_ID="654654478821"
SSL="--no-verify-ssl"

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/conversational-bi-prod"
APPRUNNER_SERVICE="conversational-bi-prod"
APPRUNNER_INSTANCE_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/talk2data-apprunner-role"
APPRUNNER_ECR_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/AppRunnerECRAccessRole"

echo "→ Checking if image exists in ECR..."
IMAGE_COUNT=$(aws ecr describe-images --repository-name "conversational-bi-prod" \
  --profile "$PROFILE" --region "$REGION" $SSL \
  --query 'length(imageDetails)' --output text 2>/dev/null || echo "0")

if [ "$IMAGE_COUNT" = "0" ] || [ "$IMAGE_COUNT" = "None" ]; then
  echo "  ERROR: No images in ECR. Wait for CodeBuild to finish first."
  exit 1
fi
echo "  ✓ Found $IMAGE_COUNT image(s) in ECR"

echo "→ Checking if App Runner service already exists..."
EXISTING=$(aws apprunner list-services \
  --profile "$PROFILE" --region "$REGION" $SSL \
  --query "ServiceSummaryList[?ServiceName=='${APPRUNNER_SERVICE}'].ServiceArn" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ] && [ "$EXISTING" != "" ]; then
  echo "  ✓ App Runner service already exists"
  URL=$(aws apprunner describe-service --service-arn "$EXISTING" \
    --profile "$PROFILE" --region "$REGION" $SSL \
    --query 'Service.ServiceUrl' --output text)
  echo "  URL: https://$URL"
  exit 0
fi

echo "→ Creating App Runner service..."
aws apprunner create-service \
  --service-name "$APPRUNNER_SERVICE" \
  --source-configuration "{
    \"AuthenticationConfiguration\": {
      \"AccessRoleArn\": \"${APPRUNNER_ECR_ROLE}\"
    },
    \"AutoDeploymentsEnabled\": true,
    \"ImageRepository\": {
      \"ImageIdentifier\": \"${ECR_URI}:latest\",
      \"ImageRepositoryType\": \"ECR\",
      \"ImageConfiguration\": {
        \"Port\": \"8001\",
        \"RuntimeEnvironmentVariables\": {
          \"AWS_REGION\": \"us-east-1\",
          \"S3_BUCKET\": \"visualization-poc-bucket\",
          \"GUARDRAIL_ID\": \"unf4323uxnff\",
          \"ENVIRONMENT\": \"prod\"
        }
      }
    }
  }" \
  --instance-configuration "{
    \"Cpu\": \"1 vCPU\",
    \"Memory\": \"2 GB\",
    \"InstanceRoleArn\": \"${APPRUNNER_INSTANCE_ROLE}\"
  }" \
  --health-check-configuration "{
    \"Protocol\": \"HTTP\",
    \"Path\": \"/health\",
    \"Interval\": 10,
    \"Timeout\": 5,
    \"HealthyThreshold\": 1,
    \"UnhealthyThreshold\": 5
  }" \
  --profile "$PROFILE" --region "$REGION" $SSL

echo ""
echo "✓ App Runner service created!"
echo "  It may take 3-5 minutes to become healthy."
echo "  Auto-deploy is enabled — future ECR pushes will trigger redeploy."
