#!/bin/bash
# Test if we can create IAM roles
PROFILE="PowerUserAccess-654654478821"

echo "=== Testing IAM create-role permission ==="
aws iam create-role \
  --role-name test-delete-me-conv-bi \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  --profile "$PROFILE" \
  --no-verify-ssl 2>&1

echo ""
echo "=== Cleanup (delete test role if created) ==="
aws iam delete-role --role-name test-delete-me-conv-bi --profile "$PROFILE" --no-verify-ssl 2>&1

echo ""
echo "=== Testing iam:PassRole (list attached policies) ==="
aws iam list-roles --profile "$PROFILE" --no-verify-ssl --query 'Roles[?starts_with(RoleName,`viz-agent`)].[RoleName]' --output text 2>&1

echo ""
echo "=== Check existing viz-agent-lambda-role (from your lambda/deploy.sh) ==="
aws iam get-role --role-name viz-agent-lambda-role --profile "$PROFILE" --no-verify-ssl --query 'Role.Arn' --output text 2>&1
