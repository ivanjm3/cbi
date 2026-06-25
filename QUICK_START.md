# Quick Start: Deploy Scheduled Reports (NO Lambda)

## Timeline: ~20 minutes total

---

## Step 1: Your Boss (5 minutes)

Share `AWS_SETUP_FOR_BOSS.md` with your AWS admin.

They run 4 commands. Done.

They provide you:
- AWS Account ID (e.g., 654654478821)
- Confirmation that it worked

---

## Step 2: You Deploy (10 minutes)

### 2a. Get Account ID
```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo $AWS_ACCOUNT_ID
```

### 2b. Deploy State Machine
```bash
aws stepfunctions create-state-machine \
  --name scheduled-report-executor \
  --definition file://infrastructure/step-functions-state-machine-simplified.json \
  --role-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:role/scheduled-report-sfn-execution-role"
```

Copy the ARN from output.

### 2c. Update `.env`
```
STEP_FUNCTIONS_STATE_MACHINE_ARN=arn:aws:states:us-east-1:YOUR_ACCOUNT_ID:stateMachine:scheduled-report-executor
EVENTBRIDGE_SCHEDULER_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT_ID:role/eventbridge-scheduler-role
```

### 2d. Restart Backend
```bash
# Kill running services
python -m src.services.scheduling_api
```

---

## Step 3: Test (5 minutes)

1. Open `http://localhost:5173/scheduled-reports`
2. Click "Create New Scheduled Report"
3. Fill in form and create
4. Click "Run Now"
5. Check execution history

**Expected**: Execution shows "success" status

---

## That's It!

Scheduled reports are live.

When you create a report with recurrence:
- EventBridge Scheduler automatically creates cron rule
- At scheduled time, Step Functions triggers
- Step Functions calls your backend API
- Backend executes query, stores result
- Frontend shows latest execution

---

## Files You Need

- `AWS_SETUP_FOR_BOSS.md` → Share with boss
- `infrastructure/step-functions-state-machine-simplified.json` → Used in deploy
- `STEP_FUNCTIONS_DEPLOYMENT_CHECKLIST.md` → Reference if stuck

---

## What Changed in Code

**Backend**: Added 1 new endpoint
- `POST /execute-scheduled-report` in `src/services/scheduling_api.py`

**Repository**: Added 1 new method
- `get_report_by_id()` in `src/services/scheduled_reports_repository.py`

**That's it.** No Lambda. No packaging. No complexity.

---

## Common Issues

| Issue | Fix |
|-------|-----|
| State machine says "does not exist" | Check ARN in `.env` is correct |
| EventBridge scheduler not working | Check `EVENTBRIDGE_SCHEDULER_ROLE_ARN` in `.env` |
| Execution fails | Check backend logs for errors |
| "Unable to assume role" | Your boss needs to re-run IAM commands |

---

## Architecture (Simple)

```
Your Report Scheduled
    ↓
EventBridge (cron time)
    ↓
Step Functions
    ↓
HTTP POST to your backend
    ↓
Backend executes query
    ↓
Done
```

No Lambda. Just HTTP calls to your backend.

---

## Bottom Line

✅ Backend: Ready (already coded)
✅ Frontend: Ready (already built)
✅ AWS Setup: Your boss does 4 commands
✅ Deploy: You run 1 command
✅ Test: Works immediately

Go live with scheduled reports in 20 minutes.
