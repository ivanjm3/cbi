# AWS Deployment — Conversational BI System

Deploys the full system using **App Runner** (backend) + **S3/CloudFront** (frontend) + **CodeBuild** (CI/CD).

## Architecture

```
                    ┌─────────────────────────────────┐
                    │       CloudFront (CDN)           │
                    │  ┌──────────┐  ┌─────────────┐  │
   Users ──────────►│  │ /*       │  │ /query      │  │
                    │  │ S3 static│  │ /sessions/* │  │
                    │  └──────────┘  └──────┬──────┘  │
                    └───────────────────────┼─────────┘
                                            │
                                            ▼
                    ┌─────────────────────────────────┐
                    │    AWS App Runner (auto-HTTPS)    │
                    │    Port 8001 (NLP API entry)      │
                    │                                   │
                    │  NLP ──► Orchestrator ──► Spoke   │
                    │  Guardrail + Visualization        │
                    └───────────────┬───────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────┐
                    │  S3 + Bedrock + Guardrails       │
                    └─────────────────────────────────┘

    ┌─────────────────────────────────────────────────────┐
    │                  CodeBuild (CI/CD)                    │
    │  Backend Project: Docker build → ECR push            │
    │  Frontend Project: npm build → S3 sync → CF inval.   │
    │                                                      │
    │  App Runner auto-deploys on ECR image update         │
    └─────────────────────────────────────────────────────┘
```

## Why App Runner?

- **No VPC/ALB/Subnets needed** — fully managed, no networking config
- **Built-in HTTPS** — automatic TLS certificate on `.awsapprunner.com` domain
- **Auto-scaling** — scales to zero if configured, scales up on traffic
- **ECR auto-deploy** — pushes to ECR trigger automatic redeploy
- **Simpler IAM** — just instance role for Bedrock/S3 access

## Prerequisites

1. **AWS CLI v2** — configured with SSO
2. **Docker** — running locally (only needed for initial deploy to seed ECR)
3. **WSL** — the deploy script runs in bash

## Quick Start (First Deploy)

```bash
# 1. Login to AWS (from WSL)
aws sso login --profile PowerUserAccess-654654478821

# 2. Run full deployment (from project root)
bash deploy/deploy.sh
```

This does:
1. Deploys CloudFormation (creates all infrastructure)
2. Builds Docker image locally and pushes to ECR (seeds App Runner)
3. App Runner detects the image and starts the service

## Subsequent Deployments (via CodeBuild)

After initial deploy, use CodeBuild for CI/CD — no local Docker needed:

```bash
# Deploy backend changes (uploads source → CodeBuild builds → ECR → App Runner auto-deploys)
bash deploy/deploy.sh --build-backend

# Deploy frontend changes (uploads source → CodeBuild builds → S3 → CloudFront invalidation)
bash deploy/deploy.sh --build-frontend

# Deploy both
bash deploy/deploy.sh --build-all
```

## Deploy Script Options

```bash
bash deploy/deploy.sh \
  --profile PowerUserAccess-654654478821 \  # AWS profile
  --region us-east-1 \                      # AWS region
  --env prod \                              # Environment (dev/staging/prod)
  --skip-infra                              # Skip CloudFormation (infra exists)
```

## What Gets Created

| Resource | Purpose |
|----------|---------|
| App Runner Service | Runs all 5 FastAPI services in one container |
| ECR Repository | Stores Docker images, triggers App Runner auto-deploy |
| S3 Bucket (frontend) | Hosts static React build |
| S3 Bucket (artifacts) | Stores source zips for CodeBuild |
| CloudFront Distribution | CDN with path-based routing (SPA + API proxy) |
| CodeBuild (backend) | Docker build + ECR push |
| CodeBuild (frontend) | npm build + S3 sync + CF invalidation |
| IAM Roles | App Runner instance role, CodeBuild role |

## How Auto-Deploy Works

```
You push code → bash deploy/deploy.sh --build-backend
                        │
                        ▼
              CodeBuild picks up source from S3
                        │
                        ▼
              Docker build + push to ECR (:latest + :commit-hash)
                        │
                        ▼
              App Runner detects new ECR image
                        │
                        ▼
              Rolling deployment (zero-downtime)
```

## Estimated Costs (us-east-1)

| Resource | Approximate Monthly Cost |
|----------|--------------------------|
| App Runner (1 vCPU, 2 GB, active) | ~$40 |
| App Runner (paused / low traffic) | ~$7 |
| CloudFront | ~$1-5 |
| S3 (frontend + artifacts) | < $1 |
| CodeBuild (on-demand) | ~$1-3 |
| ECR storage | < $1 |
| **Total (active)** | **~$45-50/month** |
| **Total (low traffic)** | **~$10-15/month** |

## Teardown

```bash
# Empty S3 buckets first (CloudFormation can't delete non-empty buckets)
aws s3 rm s3://conversational-bi-frontend-prod-654654478821 --recursive --profile PowerUserAccess-654654478821
aws s3 rm s3://conversational-bi-codebuild-prod-654654478821 --recursive --profile PowerUserAccess-654654478821

# Delete the stack
aws cloudformation delete-stack \
  --stack-name conversational-bi-prod \
  --profile PowerUserAccess-654654478821 \
  --region us-east-1
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| App Runner shows "Create failed" | Check CloudWatch logs: `/aws/apprunner/conversational-bi-prod/` |
| Health check failing | Ensure port 8001 serves `/health` returning 200 |
| Frontend shows blank page | Check S3 bucket has `index.html`, CloudFront custom error responses set |
| CodeBuild fails | Check build logs in CodeBuild console or CloudWatch |
| "Image not found" in App Runner | Ensure ECR has at least one `:latest` image (run initial deploy) |
| CORS errors in browser | Frontend uses CloudFront path routing (same-origin), shouldn't happen |
