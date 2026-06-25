#!/usr/bin/env python3
"""Deploy Step Functions state machine for scheduled reports.

Reads the ASL definition from src/services/step_functions_definition.json,
creates or updates the Step Functions state machine, and outputs the ARN
for use in environment variables.

Usage:
    python scripts/deploy_step_functions.py [--region us-east-1] [--role-arn arn:aws:iam::...]

Environment variables:
    AWS_REGION: Override region (default: us-east-1)
    AWS_ROLE_ARN: Step Functions role ARN (required if --role-arn not specified)
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import boto3

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_asl_definition(asl_path: Path) -> str:
    """Load and validate ASL definition from file.
    
    Args:
        asl_path: Path to the ASL JSON file
        
    Returns:
        ASL definition as JSON string
        
    Raises:
        FileNotFoundError: If ASL file not found
        json.JSONDecodeError: If ASL is invalid JSON
    """
    if not asl_path.exists():
        raise FileNotFoundError(f"ASL definition not found at {asl_path}")
    
    with open(asl_path, "r") as f:
        asl = json.load(f)  # Validate JSON
    
    logger.info(f"Loaded ASL definition from {asl_path}")
    return json.dumps(asl)


def deploy_state_machine(
    sfn_client,
    iam_client,
    state_machine_name: str,
    asl_definition: str,
    role_arn: str | None
) -> str:
    """Create or update Step Functions state machine.
    
    Args:
        sfn_client: boto3 Step Functions client
        iam_client: boto3 IAM client
        state_machine_name: Name of state machine
        asl_definition: ASL definition as JSON string
        role_arn: IAM role ARN for state machine (optional)
        
    Returns:
        State machine ARN
    """
    # If no role specified, try to create service-linked role
    if not role_arn:
        try:
            logger.info("Creating service-linked role for Step Functions...")
            iam_client.create_service_linked_role(
                AWSServiceName='states.amazonaws.com',
                Description='Service-linked role for Scheduled Reports Step Functions'
            )
            logger.info("Service-linked role created successfully")
        except iam_client.exceptions.InvalidInputException as e:
            if "already exists" in str(e):
                logger.info("Service-linked role already exists")
            else:
                logger.warning(f"Could not create service-linked role: {e}")
        
        # Use the service-linked role
        role_arn = "arn:aws:iam::654654478821:role/aws-service-role/states.amazonaws.com/AWSServiceRoleForStepFunctions"
    
    try:
        # Try to find existing state machine by name
        response = sfn_client.list_state_machines()
        existing_arn = None
        
        for sm in response.get('stateMachines', []):
            if sm['name'] == state_machine_name:
                existing_arn = sm['stateMachineArn']
                break
        
        if existing_arn:
            # Update existing state machine
            logger.info(f"Updating existing state machine: {state_machine_name}")
            sfn_client.update_state_machine(
                stateMachineArn=existing_arn,
                definition=asl_definition,
                roleArn=role_arn
            )
            
            logger.info(f"State machine updated: {existing_arn}")
            return existing_arn
        else:
            # Create new state machine
            logger.info(f"Creating new state machine: {state_machine_name}")
            response = sfn_client.create_state_machine(
                name=state_machine_name,
                definition=asl_definition,
                roleArn=role_arn,
                type='STANDARD'
            )
            
            state_machine_arn = response['stateMachineArn']
            logger.info(f"State machine created: {state_machine_arn}")
            return state_machine_arn
        
    except Exception as e:
        logger.error(f"Error deploying state machine: {e}")
        raise


def main():
    """Deploy Step Functions state machine."""
    parser = argparse.ArgumentParser(
        description="Deploy Step Functions state machine for scheduled reports"
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", "us-east-1"),
        help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("AWS_PROFILE"),
        help="AWS profile name (optional, uses default if not specified)"
    )
    parser.add_argument(
        "--role-arn",
        default=os.getenv("AWS_ROLE_ARN"),
        help="IAM role ARN (optional; if not specified, uses service-linked role)"
    )
    parser.add_argument(
        "--state-machine-name",
        default="scheduled-report-executor",
        help="Step Functions state machine name (default: scheduled-report-executor)"
    )
    parser.add_argument(
        "--asl-path",
        default="src/services/step_functions_definition.json",
        help="Path to ASL definition file (default: src/services/step_functions_definition.json)"
    )
    
    args = parser.parse_args()
    
    # Load ASL definition
    try:
        asl_definition = load_asl_definition(Path(args.asl_path))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load ASL definition: {e}")
        sys.exit(1)
    
    # Create AWS clients
    try:
        session = boto3.Session(
            region_name=args.region,
            profile_name=args.profile
        )
        sfn_client = session.client('stepfunctions', verify=False)
        iam_client = session.client('iam', verify=False)
    except Exception as e:
        logger.error(f"Failed to create AWS clients: {e}")
        sys.exit(1)
    
    # Use provided role ARN (optional)
    role_arn = args.role_arn
    if role_arn:
        logger.info(f"Using role: {role_arn}")
    else:
        logger.info("No role specified; will create service-linked role if needed")
    
    # Deploy state machine
    try:
        state_machine_arn = deploy_state_machine(
            sfn_client,
            iam_client,
            args.state_machine_name,
            asl_definition,
            role_arn
        )
        
        # Output ARN for shell capture
        print(f"STATE_MACHINE_ARN={state_machine_arn}")
        logger.info(f"Deployment successful!")
        logger.info(f"Export to environment: export STEP_FUNCTIONS_STATE_MACHINE_ARN={state_machine_arn}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to deploy state machine: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
