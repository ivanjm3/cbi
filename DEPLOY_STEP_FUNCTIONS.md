# Step Functions State Machine Deployment

The Scheduled Reports feature requires an AWS Step Functions state machine to orchestrate query execution.

## Pre-requisites

- AWS account with Step Functions access
- Existing IAM role: `StepFunctionsDataLakeRole` or `StepFunctionsKPIRole`
- ASL definition: `src/services/step_functions_definition.json`

## Admin: Deploy State Machine

Choose ONE method below:

### Method 1: AWS CLI (Recommended)

```bash
aws stepfunctions create-state-machine \
  --name scheduled-report-executor \
  --definition file://src/services/step_functions_definition.json \
  --role-arn arn:aws:iam::654654478821:role/StepFunctionsDataLakeRole \
  --type STANDARD \
  --region us-east-1
```

Output will include the state machine ARN. Save it.

### Method 2: AWS Console

1. Go to AWS Step Functions console
2. Click "Create state machine"
3. Choose "Standard" type
4. Paste the ASL definition from `src/services/step_functions_definition.json`
5. Set role to `StepFunctionsDataLakeRole`
6. Name: `scheduled-report-executor`
7. Create

Copy the state machine ARN from the result.

## Developer: Configure Environment

After admin provides the state machine ARN:

```bash
export STEP_FUNCTIONS_STATE_MACHINE_ARN=arn:aws:states:us-east-1:654654478821:stateMachine:scheduled-report-executor
```

Or add to `.env`:

```
STEP_FUNCTIONS_STATE_MACHINE_ARN=arn:aws:states:us-east-1:654654478821:stateMachine:scheduled-report-executor
```

Then restart the scheduling API:

```bash
python -m src.services.scheduling_api
```

## Verify

Click "Run Now" button on a scheduled report. It should trigger the state machine and execute the query.

Check Step Functions console to see execution history.

## Troubleshooting

**StateMachineDoesNotExist error**: State machine not deployed yet. Ask admin to deploy using Method 1 or 2 above.

**AccessDeniedException (PassRole)**: User doesn't have IAM PassRole permission. Admin must create the state machine, not the developer.

**EventBridge schedule fails**: Verify `EVENTBRIDGE_SCHEDULER_ROLE_ARN` is set correctly (default in code: `arn:aws:iam::654654478821:role/eventbridge-scheduler-role`).
