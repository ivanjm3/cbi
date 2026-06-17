#!/bin/bash
# Create a CloudFront distribution in front of App Runner.
# This gives a trusted *.cloudfront.net URL that Zscaler won't flag.

set -euo pipefail

PROFILE="PowerUserAccess-654654478821"
REGION="us-east-1"
SSL="--no-verify-ssl"

APPRUNNER_DOMAIN="jwxrxfzsjr.us-east-1.awsapprunner.com"

echo "→ Creating CloudFront distribution..."
echo "  Origin: $APPRUNNER_DOMAIN"
echo ""

DIST_CONFIG='{
  "CallerReference": "conversational-bi-prod-'$(date +%s)'",
  "Comment": "Conversational BI - CloudFront proxy to App Runner",
  "Enabled": true,
  "DefaultCacheBehavior": {
    "TargetOriginId": "apprunner-origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      "CachedMethods": {
        "Quantity": 2,
        "Items": ["GET", "HEAD"]
      }
    },
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3",
    "Compress": true
  },
  "Origins": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "apprunner-origin",
        "DomainName": "'"$APPRUNNER_DOMAIN"'",
        "CustomOriginConfig": {
          "HTTPSPort": 443,
          "OriginProtocolPolicy": "https-only",
          "OriginSslProtocols": {
            "Quantity": 1,
            "Items": ["TLSv1.2"]
          }
        }
      }
    ]
  },
  "PriceClass": "PriceClass_100"
}'

RESULT=$(aws cloudfront create-distribution \
  --distribution-config "$DIST_CONFIG" \
  --profile "$PROFILE" \
  --region "$REGION" \
  $SSL \
  --query "Distribution.{Id:Id,Domain:DomainName,Status:Status}" \
  --output text)

echo "✓ CloudFront distribution created!"
echo ""
echo "  $RESULT"
echo ""
echo "  Your new URL will be: https://<domain-from-above>"
echo ""
echo "  NOTE: It may take 5-15 minutes for the distribution to deploy."
echo "  Status will change from 'InProgress' to 'Deployed'."
echo ""
echo "  Check status:"
echo "    aws cloudfront list-distributions --profile $PROFILE $SSL --query \"DistributionList.Items[?Comment=='Conversational BI - CloudFront proxy to App Runner'].[DomainName,Status]\" --output text"
