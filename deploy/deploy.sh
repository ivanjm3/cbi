#!/bin/bash
# =============================================================================
# Conversational BI System — AWS Deployment (CLI-only, no CloudFormation)
#
# Reuses existing IAM roles and creates resources via AWS CLI.
# This avoids the iam:PassRole restriction in CloudFormation.
#
# Existing roles used:
#   - talk2data-apprunner-role (App Runner instance)
#   - AppRunnerECRAccessRole (App Runner ECR pull)
#   - talk2data-codebuild-role (CodeBuild service role)
#
# Usage:
#   bash deploy/deploy.sh                  # Full first-time deploy
#   bash deploy/deploy.sh --build-backend  # Rebuild backend via CodeBuild
#   bash deploy/deploy.sh --build-frontend # Rebuild frontend via CodeBuild
#   bash deploy/deploy.sh --build-all      # Both
# =============================================================================

set -euo pipefail

# ─── Config ─────────────────────────────────────────────────────────────────
PROFILE="${AWS_PROFILE:-PowerUserAccess-654654478821}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="654654478821"

# Resource names
ECR_REPO="conversational-bi-prod"
FRONTEND_BUCKET="conversational-bi-frontend-prod-${ACCOUNT_ID}"
ARTIFACT_BUCKET="conversational-bi-codebuild-prod-${ACCOUNT_ID}"
APPRUNNER_SERVICE="conversational-bi-prod"
CB_BACKEND="talk2data-build-talk2data-ui"
CB_FRONTEND="talk2data-build-talk2data-ui"

# Existing IAM roles (reuse from talk2data)
APPRUNNER_INSTANCE_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/talk2data-apprunner-role"
APPRUNNER_ECR_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/AppRunnerECRAccessRole"
CODEBUILD_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/talk2data-codebuild-role"

# Other config
S3_DATA_BUCKET="visualization-poc-bucket"
GUARDRAIL_ID="joes1p3j7sa4"

# SSL flag for corporate proxy
SSL="--no-verify-ssl"

# Action flags
DO_INFRA=true
DO_BUILD_BACKEND=false
DO_BUILD_FRONTEND=false

# ─── Parse Args ─────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --build-backend)  DO_INFRA=false; DO_BUILD_BACKEND=true; shift ;;
    --build-frontend) DO_INFRA=false; DO_BUILD_FRONTEND=true; shift ;;
    --build-all)      DO_INFRA=false; DO_BUILD_BACKEND=true; DO_BUILD_FRONTEND=true; shift ;;
    --skip-infra)     DO_INFRA=false; shift ;;
    --help)
      echo "Usage: bash deploy/deploy.sh [OPTIONS]"
      echo "  (no flags)           Full first-time deploy"
      echo "  --build-backend      Rebuild backend (CodeBuild → ECR → App Runner)"
      echo "  --build-frontend     Rebuild frontend (CodeBuild → S3)"
      echo "  --build-all          Both"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "============================================================"
echo "  Conversational BI — AWS Deployment (CLI-only)"
echo "============================================================"
echo "  Account:   $ACCOUNT_ID"
echo "  Region:    $REGION"
echo "============================================================"
echo ""

# ─── Verify credentials ────────────────────────────────────────────────────
echo "→ Verifying AWS credentials..."
aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" $SSL > /dev/null 2>&1 || {
  echo "ERROR: Run: aws sso login --profile $PROFILE"
  exit 1
}
echo "  ✓ Credentials valid"
echo ""

# =============================================================================
if [ "$DO_INFRA" = true ]; then
# =============================================================================

# ─── Step 1: ECR Repository ────────────────────────────────────────────────
echo "→ Step 1: ECR Repository..."
aws ecr describe-repositories --repository-names "$ECR_REPO" \
  --profile "$PROFILE" --region "$REGION" $SSL > /dev/null 2>&1 && {
  echo "  ✓ ECR repo already exists: $ECR_REPO"
} || {
  echo "  Creating ECR repo: $ECR_REPO"
  aws ecr create-repository --repository-name "$ECR_REPO" \
    --image-scanning-configuration scanOnPush=true \
    --profile "$PROFILE" --region "$REGION" $SSL > /dev/null
  echo "  ✓ ECR repo created"
}
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
echo "  URI: $ECR_URI"
echo ""

# ─── Step 2: S3 Buckets ────────────────────────────────────────────────────
echo "→ Step 2: S3 Buckets..."
for BUCKET in "$FRONTEND_BUCKET" "$ARTIFACT_BUCKET"; do
  aws s3api head-bucket --bucket "$BUCKET" --profile "$PROFILE" --region "$REGION" $SSL 2>/dev/null && {
    echo "  ✓ Bucket exists: $BUCKET"
  } || {
    echo "  Creating bucket: $BUCKET"
    aws s3api create-bucket --bucket "$BUCKET" \
      --profile "$PROFILE" --region "$REGION" $SSL > /dev/null
    echo "  ✓ Created: $BUCKET"
  }
done
echo ""

# ─── Step 3: Build and push Docker image ───────────────────────────────────
echo "→ Step 3: Docker Image..."
IMAGE_COUNT=$(aws ecr describe-images --repository-name "$ECR_REPO" \
  --profile "$PROFILE" --region "$REGION" $SSL \
  --query 'length(imageDetails)' --output text 2>/dev/null || echo "0")

if [ "$IMAGE_COUNT" = "0" ] || [ "$IMAGE_COUNT" = "None" ]; then
  echo "  ECR is empty — will use CodeBuild to build image (no local Docker needed)"
  echo "  → Packaging backend source..."
  TMPFILE="/tmp/backend-source-$$.zip"
  # Use tar+gzip as fallback if zip not available
  if command -v zip &> /dev/null; then
    zip -qr "$TMPFILE" \
      src/ data/ frontend/ deploy/Dockerfile deploy/buildspec-backend.yaml pyproject.toml run_all.py .dockerignore \
      -x "*/__pycache__/*" "*/.pytest_cache/*" "frontend/node_modules/*" "frontend/dist/*" 2>/dev/null
  else
    # zip not available — install it
    echo "  (Installing zip...)"
    sudo apt-get update -qq && sudo apt-get install -y -qq zip > /dev/null 2>&1 || true
    zip -qr "$TMPFILE" \
      src/ data/ frontend/ deploy/Dockerfile deploy/buildspec-backend.yaml pyproject.toml run_all.py .dockerignore \
      -x "*/__pycache__/*" "*/.pytest_cache/*" "frontend/node_modules/*" "frontend/dist/*" 2>/dev/null
  fi
  echo "  → Uploading to S3..."
  aws s3 cp "$TMPFILE" "s3://${ARTIFACT_BUCKET}/backend-source.zip" \
    --profile "$PROFILE" --region "$REGION" $SSL > /dev/null
  rm -f "$TMPFILE"
  echo "  ✓ Source uploaded — will trigger CodeBuild after projects are created"
  NEED_INITIAL_BUILD=true
else
  echo "  ✓ ECR already has $IMAGE_COUNT image(s)"
  NEED_INITIAL_BUILD=false
fi
echo ""

# ─── Step 4: App Runner ────────────────────────────────────────────────────
echo "→ Step 4: App Runner Service..."
APPRUNNER_ARN=$(aws apprunner list-services \
  --profile "$PROFILE" --region "$REGION" $SSL \
  --query "ServiceSummaryList[?ServiceName=='${APPRUNNER_SERVICE}'].ServiceArn" \
  --output text 2>/dev/null || echo "")

if [ -n "$APPRUNNER_ARN" ] && [ "$APPRUNNER_ARN" != "None" ] && [ "$APPRUNNER_ARN" != "" ]; then
  echo "  ✓ App Runner service already exists"
  APPRUNNER_URL=$(aws apprunner describe-service \
    --service-arn "$APPRUNNER_ARN" \
    --profile "$PROFILE" --region "$REGION" $SSL \
    --query 'Service.ServiceUrl' --output text)
  echo "  URL: https://$APPRUNNER_URL"
elif [ "$NEED_INITIAL_BUILD" = true ]; then
  echo "  ⏳ Skipping App Runner creation — need to build image first"
  echo "  App Runner will be created after CodeBuild pushes the first image."
  APPRUNNER_URL="pending-after-first-build"
else
  echo "  Creating App Runner service..."
  APPRUNNER_RESULT=$(aws apprunner create-service \
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
            \"S3_BUCKET\": \"${S3_DATA_BUCKET}\",
            \"GUARDRAIL_ID\": \"${GUARDRAIL_ID}\",
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
    --profile "$PROFILE" --region "$REGION" $SSL \
    --output json 2>&1)

  echo "$APPRUNNER_RESULT" | grep -q "ServiceUrl" && {
    APPRUNNER_URL=$(echo "$APPRUNNER_RESULT" | grep -o '"ServiceUrl": "[^"]*"' | cut -d'"' -f4)
    echo "  ✓ App Runner service created"
    echo "  URL: https://$APPRUNNER_URL"
    echo "  (May take 3-5 minutes to become healthy)"
  } || {
    echo "  ⚠ App Runner creation output:"
    echo "$APPRUNNER_RESULT"
    APPRUNNER_URL="creation-failed-check-output"
  }
fi
echo ""

# ─── Step 5: CodeBuild Projects ────────────────────────────────────────────
echo "→ Step 5: CodeBuild Projects..."
echo "  Using existing project: $CB_BACKEND"
echo "  (Source and buildspec will be overridden at build time)"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Infrastructure Setup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ─── Step 6: Trigger initial CodeBuild if ECR was empty ─────────────────────
if [ "$NEED_INITIAL_BUILD" = true ]; then
  echo "→ Step 6: Triggering initial backend build via CodeBuild..."
  echo "  Using project: $CB_BACKEND (with source override)"
  BUILD_ID=$(aws codebuild start-build \
    --project-name "$CB_BACKEND" \
    --source-type-override S3 \
    --source-location-override "${ARTIFACT_BUCKET}/backend-source.zip" \
    --buildspec-override "deploy/buildspec-backend.yaml" \
    --privileged-mode-override \
    --environment-variables-override '[{"name":"AWS_ACCOUNT_ID","value":"'"${ACCOUNT_ID}"'","type":"PLAINTEXT"},{"name":"ECR_REPO_URI","value":"'"${ECR_URI}"'","type":"PLAINTEXT"},{"name":"AWS_DEFAULT_REGION","value":"'"${REGION}"'","type":"PLAINTEXT"},{"name":"IMAGE_TAG","value":"latest","type":"PLAINTEXT"}]' \
    --profile "$PROFILE" --region "$REGION" $SSL \
    --query 'build.id' --output text 2>&1)

  if echo "$BUILD_ID" | grep -q "codebuild"; then
    echo "  ✓ Build started: $BUILD_ID"
    echo ""
    echo "  ⏳ Waiting for build to complete (5-10 minutes)..."
    echo "  Monitor: https://${REGION}.console.aws.amazon.com/codesuite/codebuild/projects/${CB_BACKEND}"
    echo ""
    echo "  After the build completes, run:"
    echo "    bash deploy/create-apprunner.sh"
  else
    echo "  ⚠ Build trigger failed:"
    echo "  $BUILD_ID"
    echo ""
    echo "  Alternative: install Docker Desktop, then:"
    echo "    docker build -t conversational-bi:latest -f deploy/Dockerfile ."
    echo "    aws ecr get-login-password --region us-east-1 --profile $PROFILE | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
    echo "    docker tag conversational-bi:latest ${ECR_URI}:latest"
    echo "    docker push ${ECR_URI}:latest"
    echo "    bash deploy/create-apprunner.sh"
  fi
  echo ""
fi

echo "  Backend:  https://${APPRUNNER_URL:-pending}"
echo "  ECR:      $ECR_URI"
echo "  Frontend: s3://$FRONTEND_BUCKET"
echo ""

fi
# =============================================================================
# End of infra section
# =============================================================================

# ─── CodeBuild: Backend ─────────────────────────────────────────────────────
if [ "$DO_BUILD_BACKEND" = true ]; then
  echo "═══════════════════════════════════════════════════════════"
  echo "  Triggering CodeBuild: Backend"
  echo "═══════════════════════════════════════════════════════════"
  echo ""

  ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

  echo "  → Packaging source..."
  TMPFILE="/tmp/backend-source-$$.zip"
  zip -qr "$TMPFILE" \
    src/ data/ frontend/ deploy/Dockerfile deploy/buildspec-backend.yaml pyproject.toml run_all.py .dockerignore \
    -x "*/__pycache__/*" "*/.pytest_cache/*" "frontend/node_modules/*" "frontend/dist/*" 2>/dev/null

  echo "  → Uploading to S3..."
  aws s3 cp "$TMPFILE" "s3://${ARTIFACT_BUCKET}/backend-source.zip" \
    --profile "$PROFILE" --region "$REGION" $SSL > /dev/null
  rm -f "$TMPFILE"

  echo "  → Starting build..."
  BUILD_ID=$(aws codebuild start-build \
    --project-name "$CB_BACKEND" \
    --source-type-override S3 \
    --source-location-override "${ARTIFACT_BUCKET}/backend-source.zip" \
    --buildspec-override "deploy/buildspec-backend.yaml" \
    --privileged-mode-override \
    --environment-variables-override '[{"name":"AWS_ACCOUNT_ID","value":"'"${ACCOUNT_ID}"'","type":"PLAINTEXT"},{"name":"ECR_REPO_URI","value":"'"${ECR_URI}"'","type":"PLAINTEXT"},{"name":"AWS_DEFAULT_REGION","value":"'"${REGION}"'","type":"PLAINTEXT"},{"name":"IMAGE_TAG","value":"latest","type":"PLAINTEXT"}]' \
    --profile "$PROFILE" --region "$REGION" $SSL \
    --query 'build.id' --output text)
  echo "  ✓ Build started: $BUILD_ID"
  echo ""
fi

# ─── CodeBuild: Frontend ────────────────────────────────────────────────────
if [ "$DO_BUILD_FRONTEND" = true ]; then
  echo "═══════════════════════════════════════════════════════════"
  echo "  Triggering CodeBuild: Frontend"
  echo "═══════════════════════════════════════════════════════════"
  echo ""

  echo "  → Packaging source..."
  TMPFILE="/tmp/frontend-source-$$.zip"
  zip -qr "$TMPFILE" \
    frontend/ deploy/buildspec-frontend.yaml \
    -x "frontend/node_modules/*" "frontend/dist/*" 2>/dev/null

  echo "  → Uploading to S3..."
  aws s3 cp "$TMPFILE" "s3://${ARTIFACT_BUCKET}/frontend-source.zip" \
    --profile "$PROFILE" --region "$REGION" $SSL > /dev/null
  rm -f "$TMPFILE"

  echo "  → Starting build..."
  BUILD_ID=$(aws codebuild start-build \
    --project-name "$CB_FRONTEND" \
    --source-type-override S3 \
    --source-location-override "${ARTIFACT_BUCKET}/frontend-source.zip" \
    --buildspec-override "deploy/buildspec-frontend.yaml" \
    --environment-variables-override '[{"name":"FRONTEND_BUCKET","value":"'"${FRONTEND_BUCKET}"'","type":"PLAINTEXT"},{"name":"CLOUDFRONT_DISTRIBUTION_ID","value":"none","type":"PLAINTEXT"},{"name":"VITE_API_BASE","value":"","type":"PLAINTEXT"}]' \
    --profile "$PROFILE" --region "$REGION" $SSL \
    --query 'build.id' --output text)
  echo "  ✓ Build started: $BUILD_ID"
  echo ""
fi

# ─── Summary ────────────────────────────────────────────────────────────────
echo "============================================================"
echo "  ✓ Done!"
echo "============================================================"
echo ""
echo "  Subsequent deploys:"
echo "    bash deploy/deploy.sh --build-backend"
echo "    bash deploy/deploy.sh --build-frontend"
echo "    bash deploy/deploy.sh --build-all"
echo ""
echo "============================================================"
