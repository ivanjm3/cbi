# Step Functions Setup & Deployment Guide

## Overview

This guide walks you through setting up and deploying the AWS infrastructure needed for scheduled report execution using Step Functions and EventBridge Scheduler.

## Architecture

```
Scheduled Report Creation
        ↓
EventBridge Scheduler (cron rule per report)
        ↓
Triggers Step Functions Execution
        ↓
Step Functions State Machine
  1. Validate report is active
  2. Fetch report configuration
  3. Fetch original chat query
  4. Execute query via NLP API
  5. Store execution result
  6. Update report with latest execution
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials
3. **IAM User/Role** with permissions to:
   - Create/manage Step Functions state machines
   - Create/manage EventBridge Scheduler rules
   - Create/manage IAM roles and policies
   - Create Lambda functions
   - Access S3 buckets

## Step 1: Create IAM Roles

### 1a. Step Functions Execution Role

This role allows Step Functions to invoke Lambda functions and access AWS services.

```bash
# Create the trust policy JSON
cat > /tmp/sfn-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "states.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
  --role-name scheduled-report-sfn-execution-role \
  --assume-role-policy-document file:///tmp/sfn-trust-policy.json
```

### 1b. Step Functions Execution Policy

This policy grants permissions for Step Functions to invoke Lambda and access services.

```bash
# Create inline policy
cat > /tmp/sfn-execution-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": [
        "arn:aws:lambda:us-east-1:*:function:fetch-report-config",
        "arn:aws:lambda:us-east-1:*:function:fetch-chat-query",
        "arn:aws:lambda:us-east-1:*:function:execute-scheduled-query",
        "arn:aws:lambda:us-east-1:*:function:store-execution-result"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/scheduled-reports*"
    }
  ]
}
EOF

# Attach policy to role
aws iam put-role-policy \
  --role-name scheduled-report-sfn-execution-role \
  --policy-name scheduled-report-sfn-execution-policy \
  --policy-document file:///tmp/sfn-execution-policy.json
```

### 1c. EventBridge Scheduler Execution Role

This role allows EventBridge Scheduler to invoke Step Functions.

```bash
# Create trust policy
cat > /tmp/scheduler-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "scheduler.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name eventbridge-scheduler-role \
  --assume-role-policy-document file:///tmp/scheduler-trust-policy.json
```

### 1d. EventBridge Scheduler Policy

```bash
# Create inline policy
cat > /tmp/scheduler-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "states:StartExecution"
      ],
      "Resource": "arn:aws:states:us-east-1:*:stateMachine:scheduled-report-executor"
    }
  ]
}
EOF

# Attach policy
aws iam put-role-policy \
  --role-name eventbridge-scheduler-role \
  --policy-name eventbridge-scheduler-policy \
  --policy-document file:///tmp/scheduler-policy.json
```

## Step 2: Create Lambda Functions

The Step Functions state machine calls four Lambda functions. You need to package and deploy them.

### 2a. Create deployment package

```bash
# Create lambda directory structure
mkdir -p lambda-deployment/lambda_functions
cp infrastructure/lambda-functions/*.py lambda-deployment/

# Install dependencies
cd lambda-deployment
pip install -r ../requirements.txt -t .

# Create deployment package
zip -r function-deployment.zip .
```

### 2b. Deploy Lambda Functions

```bash
# Get your AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1

# 1. fetch-report-config
aws lambda create-function \
  --function-name fetch-report-config \
  --runtime python3.12 \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/lambda-scheduled-reports-role \
  --handler lambda_functions.fetch_report_config.lambda_handler \
  --zip-file fileb://function-deployment.zip \
  --timeout 60 \
  --memory-size 256

# 2. fetch-chat-query
aws lambda create-function \
  --function-name fetch-chat-query \
  --runtime python3.12 \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/lambda-scheduled-reports-role \
  --handler lambda_functions.fetch_chat_query.lambda_handler \
  --zip-file fileb://function-deployment.zip \
  --timeout 60 \
  --memory-size 256

# 3. execute-scheduled-query
aws lambda create-function \
  --function-name execute-scheduled-query \
  --runtime python3.12 \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/lambda-scheduled-reports-role \
  --handler lambda_functions.execute_scheduled_query.lambda_handler \
  --zip-file fileb://function-deployment.zip \
  --timeout 300 \
  --memory-size 512

# 4. store-execution-result
aws lambda create-function \
  --function-name store-execution-result \
  --runtime python3.12 \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/lambda-scheduled-reports-role \
  --handler lambda_functions.store_execution_result.lambda_handler \
  --zip-file fileb://function-deployment.zip \
  --timeout 60 \
  --memory-size 256
```

## Step 3: Create Step Functions State Machine

```bash
# Get your AWS account ID and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1

# Get Step Functions execution role ARN
SFN_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/scheduled-report-sfn-execution-role"

# Substitute variables in state machine definition
sed -e "s/\${AWS_REGION}/${AWS_REGION}/g" \
    -e "s/\${AWS_ACCOUNT_ID}/${AWS_ACCOUNT_ID}/g" \
    infrastructure/step-functions-state-machine.json > /tmp/state-machine.json

# Create the state machine
aws stepfunctions create-state-machine \
  --name scheduled-report-executor \
  --definition file:///tmp/state-machine.json \
  --role-arn ${SFN_ROLE_ARN}
```

## Step 4: Update Backend Configuration

Update your backend configuration to use the deployed Step Functions state machine:

```bash
# Set environment variables
export STEP_FUNCTIONS_STATE_MACHINE_ARN="arn:aws:states:us-east-1:${AWS_ACCOUNT_ID}:stateMachine:scheduled-report-executor"
export EVENTBRIDGE_SCHEDULER_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/eventbridge-scheduler-role"

# Store in .env file
cat >> .env << EOF
STEP_FUNCTIONS_STATE_MACHINE_ARN=arn:aws:states:us-east-1:${AWS_ACCOUNT_ID}:stateMachine:scheduled-report-executor
EVENTBRIDGE_SCHEDULER_ROLE_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:role/eventbridge-scheduler-role
EOF
```

## Step 5: Test the Setup

### 5a. Manually trigger a state machine execution

```bash
# Get the state machine ARN
STATE_MACHINE_ARN="arn:aws:states:us-east-1:${AWS_ACCOUNT_ID}:stateMachine:scheduled-report-executor"

# Start a test execution
aws stepfunctions start-execution \
  --state-machine-arn ${STATE_MACHINE_ARN} \
  --input '{"report_id": "test-123"}' \
  --name test-execution-$(date +%s)
```

### 5b. Check execution status

```bash
# List executions
aws stepfunctions list-executions \
  --state-machine-arn ${STATE_MACHINE_ARN}

# Get execution details
aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:us-east-1:${AWS_ACCOUNT_ID}:execution:scheduled-report-executor:test-execution-1234567890
```

## Step 6: Create a Test Scheduled Report

Now that infrastructure is deployed, create a test report through the frontend:

1. Open http://localhost:5173/scheduled-reports
2. Click "Create Scheduled Report"
3. Fill in title, description
4. Set recurrence (e.g., "Daily at 10 AM")
5. Click "Create Report"

The backend should now successfully:
- Create the report in S3
- Create an EventBridge Scheduler rule
- Return success (instead of 503 error)

## Verification Checklist

- [ ] IAM roles created successfully
- [ ] Lambda functions deployed
- [ ] Step Functions state machine created
- [ ] Environment variables set in backend
- [ ] Test report created without 503 errors
- [ ] EventBridge Scheduler rule appears in AWS Console
- [ ] Manual state machine execution completes successfully

## Troubleshooting

### Issue: "State Machine Does Not Exist"

**Cause**: State machine ARN doesn't match the deployed machine

**Fix**:
```bash
# List your state machines
aws stepfunctions list-state-machines --region us-east-1

# Update the ARN in your .env file
```

### Issue: "Lambda function not found"

**Cause**: Lambda function name or ARN doesn't match

**Fix**:
```bash
# List your Lambda functions
aws lambda list-functions --region us-east-1

# Update the ARN in the state machine definition
```

### Issue: EventBridge Scheduler rule not created

**Cause**: IAM role permissions issue

**Fix**:
```bash
# Verify role has correct policy
aws iam get-role-policy \
  --role-name eventbridge-scheduler-role \
  --policy-name eventbridge-scheduler-policy

# Check backend logs for permission errors
```

## Next Steps

1. **Test manual execution**: Use "Run Now" button to trigger execution
2. **Monitor executions**: Check CloudWatch logs for Step Functions
3. **Set up notifications**: Configure SNS for failed executions
4. **Production deployment**: Use CloudFormation/IaC for infrastructure

## Cleanup (when needed)

```bash
# Delete state machine
aws stepfunctions delete-state-machine \
  --state-machine-arn arn:aws:states:us-east-1:${AWS_ACCOUNT_ID}:stateMachine:scheduled-report-executor

# Delete Lambda functions
aws lambda delete-function --function-name fetch-report-config
aws lambda delete-function --function-name fetch-chat-query
aws lambda delete-function --function-name execute-scheduled-query
aws lambda delete-function --function-name store-execution-result

# Delete IAM roles
aws iam delete-role-policy --role-name scheduled-report-sfn-execution-role --policy-name scheduled-report-sfn-execution-policy
aws iam delete-role --role-name scheduled-report-sfn-execution-role

aws iam delete-role-policy --role-name eventbridge-scheduler-role --policy-name eventbridge-scheduler-policy
aws iam delete-role --role-name eventbridge-scheduler-role
```
