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
                    │              │                    │
                    │              ├──► MCP Adapter ──► MCP Servers
                    │              │    (port 8012)     │
                    │  Guardrail + Visualization        │
                    └───────────────┬───────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────┐
                    │  S3 + Bedrock + Guardrails       │
                    │  + Redshift Data API             │
                    └─────────────────────────────────┘
```

## Services (Single Container)

| Service | Port | Description |
|---------|------|-------------|
| NLP Translator | 8001 | Entry point, natural language → structured intent |
| Orchestrator Hub | 8002 | Routes intents to spoke agents or MCP adapter |
| Guardrail Layer | 8003 | Bedrock guardrails safety layer |
| Visualization Renderer | 8004 | Chart/table rendering |
| Spoke Agent (S3) | 8010 | Legacy JSON/CSV data agent |
| Redshift Spoke Agent | 8011 | Legacy Redshift query agent |
| **MCP Adapter** | **8012** | **Bridges Orchestrator ↔ MCP servers (Redshift + S3)** |

## MCP Adapter Layer

The MCP Adapter is a new service that bridges the Orchestrator Hub with external MCP servers for data access. It supports:

- **Redshift MCP Server** — translates intents to SQL via MCP tool calls
- **S3 MCP Server** — reads datasets from S3 via MCP tool calls
- **Automatic fallback** — if MCP servers are unavailable, routes to legacy spoke agents
- **Feature flag routing** — controlled via environment variables (hot-toggleable)

### MCP Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MCP_ADAPTER` | `false` | Global toggle for MCP routing |
| `USE_MCP_REDSHIFT` | `false` | Per-datasource: route Redshift queries via MCP |
| `USE_MCP_S3` | `false` | Per-datasource: route S3 queries via MCP |

### MCP Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ADAPTER_REDSHIFT_TRANSPORT` | `stdio` | Transport: `stdio` or `streamable-http` |
| `MCP_ADAPTER_REDSHIFT_HOST` | (empty) | Host for streamable-http mode |
| `MCP_ADAPTER_REDSHIFT_PORT` | (empty) | Port for streamable-http mode |
| `MCP_ADAPTER_REDSHIFT_COMMAND` | (empty) | Executable for stdio mode |
| `MCP_ADAPTER_REDSHIFT_TIMEOUT` | `30` | Tool call timeout in seconds |
| `MCP_ADAPTER_S3_TRANSPORT` | `stdio` | Transport: `stdio` or `streamable-http` |
| `MCP_ADAPTER_S3_HOST` | (empty) | Host for streamable-http mode |
| `MCP_ADAPTER_S3_PORT` | (empty) | Port for streamable-http mode |
| `MCP_ADAPTER_S3_COMMAND` | (empty) | Executable for stdio mode |
| `MCP_ADAPTER_S3_TIMEOUT` | `30` | Tool call timeout in seconds |

## Why App Runner?

- **No VPC/ALB/Subnets needed** — fully managed, no networking config
- **Built-in HTTPS** — automatic TLS certificate on `.awsapprunner.com` domain
- **Auto-scaling** — scales to zero if configured, scales up on traffic
- **ECR auto-deploy** — pushes to ECR trigger automatic redeploy
- **Simpler IAM** — just instance role for Bedrock/S3/Redshift access

## Prerequisites

1. **AWS CLI v2** — configured with SSO
2. **Docker** — running locally (only needed for initial deploy to seed ECR)
3. **WSL/Git Bash** — the deploy script runs in bash

## Quick Start (First Deploy)

```bash
# 1. Login to AWS (from WSL or Git Bash)
aws sso login --profile PowerUserAccess-654654478821

# 2. Run full deployment (from project root)
bash deploy/deploy.sh
```

This does:
1. Creates ECR repository and S3 buckets
2. Packages source and triggers CodeBuild (Docker build → ECR push)
3. Creates App Runner service pointing to ECR image
4. App Runner auto-deploys when the image lands

## Subsequent Deployments (via CodeBuild)

After initial deploy, use CodeBuild for CI/CD — no local Docker needed:

```bash
# Deploy backend changes (uploads source → CodeBuild builds → ECR → App Runner auto-deploys)
bash deploy/deploy.sh --build-backend

# Deploy frontend changes (uploads source → CodeBuild builds → S3 → CloudFront invalidation)
bash deploy/deploy.sh --build-frontend

# Deploy both
bash deploy/deploy.sh --build-all

# Deploy with MCP enabled
bash deploy/deploy.sh --build-backend --enable-mcp
```

## Enabling MCP Routing

MCP routing is disabled by default. The system uses legacy spoke agents until you explicitly enable it.

### Option 1: Deploy with MCP enabled

```bash
bash deploy/deploy.sh --build-backend --enable-mcp
```

### Option 2: Set env vars before deploy

```bash
export USE_MCP_ADAPTER=true
export USE_MCP_REDSHIFT=true
export USE_MCP_S3=true

# Configure MCP server transport (e.g., streamable-http for remote servers)
export MCP_ADAPTER_REDSHIFT_TRANSPORT=streamable-http
export MCP_ADAPTER_REDSHIFT_HOST=your-mcp-redshift-server.internal
export MCP_ADAPTER_REDSHIFT_PORT=3000

bash deploy/update-apprunner.sh
```

### Option 3: Update env vars in AWS Console

Navigate to App Runner → conversational-bi-prod → Configuration → Environment Variables and set the flags to `true`.

## Deploy Script Options

```bash
bash deploy/deploy.sh [OPTIONS]
  (no flags)           Full first-time deploy
  --build-backend      Rebuild backend (CodeBuild → ECR → App Runner)
  --build-frontend     Rebuild frontend (CodeBuild → S3)
  --build-all          Both
  --enable-mcp         Enable MCP adapter routing (sets all flags)
  --skip-infra         Skip infrastructure creation
  --help               Show help
```

## What Gets Created

| Resource | Purpose |
|----------|---------|
| App Runner Service | Runs all 7 FastAPI services in one container |
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

# Delete App Runner service
aws apprunner delete-service \
  --service-arn <your-service-arn> \
  --profile PowerUserAccess-654654478821 \
  --region us-east-1
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| App Runner shows "Create failed" | Check CloudWatch logs: `/aws/apprunner/conversational-bi-prod/` |
| Health check failing | Ensure port 8001 serves `/health` returning 200 |
| MCP Adapter unhealthy | Check `/health` on port 8012 — shows MCP server status |
| MCP servers unavailable | Verify `MCP_ADAPTER_*` env vars; adapter falls back to legacy agents |
| Frontend shows blank page | Check S3 bucket has `index.html`, CloudFront custom error responses set |
| CodeBuild fails | Check build logs in CodeBuild console or CloudWatch |
| "Image not found" in App Runner | Ensure ECR has at least one `:latest` image (run initial deploy) |
| CORS errors in browser | Frontend uses CloudFront path routing (same-origin), shouldn't happen |
| `mcp` package install fails | Dockerfile has `|| true` fallback — adapter starts but MCP unavailable |
