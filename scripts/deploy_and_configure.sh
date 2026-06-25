#!/bin/bash

# Deploy Step Functions state machine and configure environment variables
# Usage: ./scripts/deploy_and_configure.sh [--region us-east-1] [--role-arn arn:aws:iam::...]

set -e

REGION="${AWS_REGION:-us-east-1}"
ROLE_ARN="${AWS_ROLE_ARN:-}"
ENV_FILE=".env"

echo "=== Step Functions Deployment ==="
echo "Region: $REGION"
echo ""

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --region)
      REGION="$2"
      shift 2
      ;;
    --role-arn)
      ROLE_ARN="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Run deployment script
echo "Deploying state machine..."
DEPLOY_OUTPUT=$(python scripts/deploy_step_functions.py --region "$REGION" ${ROLE_ARN:+--role-arn "$ROLE_ARN"} 2>&1 | grep "STATE_MACHINE_ARN=")

if [ -z "$DEPLOY_OUTPUT" ]; then
  echo "ERROR: Deployment failed"
  exit 1
fi

# Extract ARN
STATE_MACHINE_ARN=$(echo "$DEPLOY_OUTPUT" | cut -d'=' -f2)

echo ""
echo "✓ State machine deployed successfully"
echo "  ARN: $STATE_MACHINE_ARN"
echo ""

# Update .env file
echo "Updating $ENV_FILE..."

if [ -f "$ENV_FILE" ]; then
  # Remove existing STEP_FUNCTIONS_STATE_MACHINE_ARN if present
  sed -i.bak '/^STEP_FUNCTIONS_STATE_MACHINE_ARN=/d' "$ENV_FILE"
  rm -f "${ENV_FILE}.bak"
else
  echo "Creating $ENV_FILE..."
  touch "$ENV_FILE"
fi

# Append new ARN
echo "STEP_FUNCTIONS_STATE_MACHINE_ARN=$STATE_MACHINE_ARN" >> "$ENV_FILE"

echo "✓ Environment updated: STEP_FUNCTIONS_STATE_MACHINE_ARN=$STATE_MACHINE_ARN"
echo ""
echo "Next steps:"
echo "1. Verify .env contains the new ARN:"
echo "   grep STEP_FUNCTIONS_STATE_MACHINE_ARN .env"
echo ""
echo "2. Restart the scheduling API service:"
echo "   python -m src.services.scheduling_api"
echo ""
echo "3. Test 'Run Now' button in the UI"
