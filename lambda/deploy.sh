#!/bin/bash
# Deploy viz-agent-emit-chart Lambda function
# Usage: bash lambda/deploy.sh

set -e

PROFILE="PowerUserAccess-654654478821"
FUNCTION_NAME="viz-agent-emit-chart"
REGION="us-east-1"
RUNTIME="python3.12"
ARCHITECTURE="arm64"
TIMEOUT=30
ROLE_NAME="viz-agent-lambda-role"

echo "=== Step 1: Package the Lambda code ==="
cd lambda
zip -j function.zip lambda_function.py
cd ..
echo "✓ Created lambda/function.zip"

echo ""
echo "=== Step 2: Create IAM execution role ==="

# Trust policy for Lambda
cat > lambda/trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role (will error if it already exists — that's fine)
aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document file://lambda/trust-policy.json \
  --profile "$PROFILE" \
  2>/dev/null && echo "✓ Created role: $ROLE_NAME" || echo "⚠ Role already exists (continuing)"

# Attach basic Lambda execution policy
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" \
  --profile "$PROFILE" \
  2>/dev/null && echo "✓ Attached AWSLambdaBasicExecutionRole" || echo "⚠ Policy already attached"

# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --profile "$PROFILE" --query 'Role.Arn' --output text)
echo "  Role ARN: $ROLE_ARN"

# Wait for role propagation
echo "  Waiting 10s for IAM role propagation..."
sleep 10

echo ""
echo "=== Step 3: Create the Lambda function ==="

aws lambda create-function \
  --function-name "$FUNCTION_NAME" \
  --runtime "$RUNTIME" \
  --architectures "$ARCHITECTURE" \
  --role "$ROLE_ARN" \
  --handler "lambda_function.lambda_handler" \
  --zip-file fileb://lambda/function.zip \
  --timeout "$TIMEOUT" \
  --region "$REGION" \
  --profile "$PROFILE" \
  2>/dev/null && echo "✓ Created Lambda function: $FUNCTION_NAME" || {
    echo "⚠ Function may already exist. Updating code instead..."
    aws lambda update-function-code \
      --function-name "$FUNCTION_NAME" \
      --zip-file fileb://lambda/function.zip \
      --region "$REGION" \
      --profile "$PROFILE"
    echo "✓ Updated Lambda function code"
  }

echo ""
echo "=== Step 4: Add resource-based policy for Bedrock ==="

# Get account ID
ACCOUNT_ID=$(aws sts get-caller-identity --profile "$PROFILE" --query 'Account' --output text)
echo "  Account ID: $ACCOUNT_ID"

aws lambda add-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id "AllowBedrockAgentInvoke" \
  --action "lambda:InvokeFunction" \
  --principal "bedrock.amazonaws.com" \
  --source-arn "arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:agent/*" \
  --region "$REGION" \
  --profile "$PROFILE" \
  2>/dev/null && echo "✓ Added Bedrock invoke permission" || echo "⚠ Permission already exists"

echo ""
echo "=== Step 5: Verify deployment ==="

aws lambda get-function \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --query '{FunctionName: Configuration.FunctionName, Runtime: Configuration.Runtime, State: Configuration.State, ARN: Configuration.FunctionArn}' \
  --output table

echo ""
echo "=== Done! ==="
echo ""
echo "Lambda ARN: arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"
echo ""
echo "Next steps:"
echo "  1. Go to Bedrock Console → Agents → your agent → Action Groups"
echo "  2. Select this Lambda: $FUNCTION_NAME"
echo "  3. Upload the OpenAPI schema (emit_chart_openapi.json)"
echo "  4. Click Prepare, then Test"
