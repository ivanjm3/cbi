# Step Functions Deployment Guide - NO LAMBDA FUNCTIONS

This guide contains ONLY the AWS CLI commands needed to set up Step Functions automation.

**IMPORTANT**: Your boss needs to run the commands in the "IAM Setup" section. You run everything else locally.

---

## Architecture (Simplified)

```
User Creates Report
        ↓
EventBridge Scheduler (cron rule)
        ↓
Triggers Step Functions Execution
        ↓
Step Functions calls HTTP endpoint
        ↓
Backend API (http://localhost:8005/execute-scheduled-report)
        ↓
Backend handles: fetch config → execute query → store results
```

**No Lambda functions needed.**

---

## PART 1: IAM SETUP (YOUR BOSS RUNS THIS)

Your boss needs to run these AWS CLI commands. They create 2 IAM roles with permissions.

### 1a. Create Step Functions Execution Role

```bash
aws iam create-role \
  --role-name scheduled-report-sfn-execution-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "states.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'
```

**Expected output**: Role ARN like `arn:aws:iam::654654478821:role/scheduled-report-sfn-execution-role`

### 1b. Attach Policy to Step Functions Role

```bash
aws iam put-role-policy \
  --role-name scheduled-report-sfn-execution-role \
  --policy-name scheduled-report-sfn-execution-policy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["states:StartExecution"],
      "Resource": "arn:aws:states:us-east-1:*:stateMachine:scheduled-report-executor"
    }]
  }'
```

### 1c. Create EventBridge Scheduler Role

```bash
aws iam create-role \
  --role-name eventbridge-scheduler-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "scheduler.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'
```

**Expected output**: Role ARN like `arn:aws:iam::654654478821:role/eventbridge-scheduler-role`

### 1d. Attach Policy to Scheduler Role

```bash
aws iam put-role-policy \
  --role-name eventbridge-scheduler-role \
  --policy-name eventbridge-scheduler-policy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["states:StartExecution"],
      "Resource": "arn:aws:states:us-east-1:*:stateMachine:scheduled-report-executor"
    }]
  }'
```

---

## PART 2: DEPLOY STATE MACHINE (YOU RUN THIS LOCALLY)

Once your boss has completed Part 1, run these commands locally.

### 2a. Get Your AWS Account ID

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo $AWS_ACCOUNT_ID
```

**Copy the output, you'll need it in the next step.**

### 2b. Create Step Functions State Machine

Replace `YOUR_AWS_ACCOUNT_ID` with the account ID from step 2a:

```bash
AWS_ACCOUNT_ID=YOUR_AWS_ACCOUNT_ID
AWS_REGION=us-east-1

# Create state machine
aws stepfunctions create-state-machine \
  --name scheduled-report-executor \
  --definition '{
    "Comment": "Scheduled Report Executor - Calls backend API directly",
    "StartAt": "ExecuteScheduledReport",
    "States": {
      "ExecuteScheduledReport": {
        "Type": "Task",
        "Resource": "arn:aws:states:::http:post",
        "Parameters": {
          "ApiEndpoint": "http://localhost:8005/execute-scheduled-report",
          "Method": "POST",
          "Headers": {"Content-Type": "application/json"},
          "RequestBody": {"report_id.$": "$.report_id"}
        },
        "Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": 1, "MaxAttempts": 2, "BackoffRate": 5.0}],
        "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "ExecutionFailed", "ResultPath": "$.error"}],
        "Next": "ExecutionSucceeded"
      },
      "ExecutionSucceeded": {"Type": "Succeed"},
      "ExecutionFailed": {"Type": "Fail", "Error": "ScheduledReportExecutionFailed", "Cause.$": "$.error.Cause"}
    }
  }' \
  --role-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:role/scheduled-report-sfn-execution-role" \
  --region $AWS_REGION
```

**Expected output**: State machine ARN like `arn:aws:states:us-east-1:654654478821:stateMachine:scheduled-report-executor`

---

## PART 3: CONFIGURE BACKEND (YOU RUN THIS LOCALLY)

### 3a. Set Environment Variables

Add these to your `.env` file (or `.env.local`):

```bash
STEP_FUNCTIONS_STATE_MACHINE_ARN=arn:aws:states:us-east-1:YOUR_AWS_ACCOUNT_ID:stateMachine:scheduled-report-executor
EVENTBRIDGE_SCHEDULER_ROLE_ARN=arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/eventbridge-scheduler-role
```

Replace `YOUR_AWS_ACCOUNT_ID` with your actual account ID.

### 3b. Restart Backend

```bash
# Kill the running Scheduling API
# Then restart it:
python -m src.services.scheduling_api

# OR if using the run script:
python run_all.py
```

---

## PART 4: TEST DEPLOYMENT (YOU RUN THIS LOCALLY)

### 4a. Create a Test Scheduled Report

1. Open browser: `http://localhost:5173/scheduled-reports`
2. Click "Create New Scheduled Report"
3. Fill in:
   - Title: "Test Report"
   - Select a chat from your current session
   - Select a pinned card
   - Set recurrence: "Daily at 9 AM"
   - Click "Create"

**Expected result**: Report created successfully (no 503 error)

### 4b. Verify EventBridge Scheduler Rule Created

```bash
aws scheduler list-schedules --region us-east-1 | grep "scheduled-report"
```

**Expected output**: Shows your scheduled report rule

### 4c. Click "Run Now" to Test Execution

1. Go to your test report detail page
2. Click "Run Now"
3. Check backend logs for execution

**Expected result**: Execution completes without errors

### 4d. View Execution History

1. Scroll down in the detail page to see "Execution History"
2. You should see your test execution with status "success"

---

## TROUBLESHOOTING

### Issue: "State Machine Does Not Exist"

**Solution**: Verify the ARN in your .env file matches the created state machine:

```bash
aws stepfunctions list-state-machines --region us-east-1
```

Copy the correct ARN to `.env`:

```bash
STEP_FUNCTIONS_STATE_MACHINE_ARN=<correct-arn-from-above>
```

### Issue: EventBridge Scheduler Rule Not Created

**Solution**: Check your .env for the scheduler role ARN:

```bash
aws iam list-roles | grep eventbridge-scheduler-role
```

Make sure the ARN in `.env` matches exactly.

### Issue: "Unable to assume role" when creating state machine

**Solution**: Your boss needs to run the IAM setup commands again. The role might not have had time to propagate.

---

## CLEANUP (IF NEEDED)

To delete everything:

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Delete state machine
aws stepfunctions delete-state-machine \
  --state-machine-arn arn:aws:states:us-east-1:${AWS_ACCOUNT_ID}:stateMachine:scheduled-report-executor

# Delete EventBridge schedules (will be deleted when reports are deleted via API)

# Delete IAM policies
aws iam delete-role-policy \
  --role-name scheduled-report-sfn-execution-role \
  --policy-name scheduled-report-sfn-execution-policy

aws iam delete-role-policy \
  --role-name eventbridge-scheduler-role \
  --policy-name eventbridge-scheduler-policy

# Delete IAM roles
aws iam delete-role --role-name scheduled-report-sfn-execution-role
aws iam delete-role --role-name eventbridge-scheduler-role
```

---

## SUMMARY

✅ **Backend changes made**:
- Added `/execute-scheduled-report` endpoint to Scheduling API
- Endpoint receives report_id from Step Functions, executes query, stores results

✅ **What your boss runs**:
- Creates 2 IAM roles (4 AWS CLI commands)

✅ **What you run locally**:
- Deploy state machine (1 AWS CLI command)
- Set environment variables (update .env)
- Test via frontend

✅ **Architecture**:
- No Lambda functions needed
- Step Functions calls your running backend API directly
- Backend handles all execution logic
