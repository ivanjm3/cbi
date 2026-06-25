"""
Lambda function to fetch scheduled report configuration from S3.
Called by Step Functions during scheduled report execution.
"""
import json
import boto3
from src.services.scheduled_reports_repository import ScheduledReportsRepository

s3 = boto3.client('s3')
reports_repo = ScheduledReportsRepository()


def lambda_handler(event, context):
    """
    Fetch the report configuration.
    
    Input:
    {
        "report_id": "uuid-123"
    }
    
    Output:
    {
        "report_id": "uuid-123",
        "config": {
            "title": "...",
            "original_chat_id": "...",
            "pinned_visualization_ids": [...],
            "structured_intents": {...},
            "recurrence_pattern": {...}
        }
    }
    """
    report_id = event.get('report_id')
    
    if not report_id:
        raise ValueError('report_id is required')
    
    try:
        # Extract user_id from report_id or fetch from index
        # For now, we'll use a placeholder user_id from the report metadata
        report = reports_repo.get_report_by_id(report_id)
        
        if not report:
            raise ValueError(f'Report not found: {report_id}')
        
        if report.deleted_at is not None:
            raise ValueError(f'Report has been deleted: {report_id}')
        
        return {
            'report_id': report_id,
            'config': report.model_dump()
        }
    except Exception as e:
        print(f'Error fetching report config: {e}')
        raise


if __name__ == '__main__':
    # For local testing
    result = lambda_handler({'report_id': 'test-123'}, None)
    print(json.dumps(result, indent=2))
