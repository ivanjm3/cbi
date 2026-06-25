"""AWS Lambda handler for executing scheduled reports.

This Lambda is invoked by Step Functions state machine and calls the
Scheduling API /execute-scheduled-report endpoint to execute a scheduled report.

Deploy as:
  aws lambda create-function \
    --function-name scheduled-report-executor \
    --runtime python3.12 \
    --role arn:aws:iam::654654478821:role/StepFunctionsDataLakeRole \
    --handler scheduled_report_lambda.lambda_handler \
    --zip-file fileb://lambda.zip
"""

import json
import logging
import os
import httpx

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SCHEDULING_API_ENDPOINT = os.getenv("SCHEDULING_API_ENDPOINT", "http://localhost:8005")


def lambda_handler(event, context):
    """Execute a scheduled report.
    
    Args:
        event: Step Functions input with report_id
        context: Lambda context
        
    Returns:
        dict with execution status
    """
    try:
        report_id = event.get("report_id")
        if not report_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "report_id is required"})
            }
        
        logger.info(f"Executing scheduled report: {report_id}")
        
        # Call scheduling API endpoint
        url = f"{SCHEDULING_API_ENDPOINT}/execute-scheduled-report"
        payload = {"report_id": report_id}
        headers = {"Content-Type": "application/json"}
        
        response = httpx.post(url, json=payload, headers=headers, timeout=300)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Execution successful for report {report_id}: {result}")
            return {
                "statusCode": 200,
                "body": json.dumps(result)
            }
        else:
            error_msg = f"API returned {response.status_code}: {response.text[:200]}"
            logger.error(f"Execution failed for report {report_id}: {error_msg}")
            raise Exception(error_msg)
    
    except Exception as e:
        logger.error(f"Error executing scheduled report: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
