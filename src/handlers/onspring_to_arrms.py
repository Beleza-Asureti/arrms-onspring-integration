"""
Onspring to ARRMS Sync Handler

Retrieves data from Onspring and pushes to ARRMS.
Can be triggered via API or scheduled execution.
"""

import json
from typing import Dict, Any, List, Optional
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from adapters.onspring_client import OnspringClient
from adapters.arrms_client import ARRMSClient
from utils.exceptions import ValidationError, IntegrationError
from utils.response_builder import build_response

logger = Logger()
tracer = Tracer()
metrics = Metrics()


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Lambda handler for syncing data from Onspring to ARRMS.

    Args:
        event: API Gateway event or EventBridge event for scheduled execution
        context: Lambda context object

    Returns:
        API Gateway response with sync results
    """
    try:
        logger.info("Starting Onspring to ARRMS sync")

        # Parse request parameters
        params = parse_event(event)

        app_id = params.get('app_id')
        filter_criteria = params.get('filter', {})
        batch_size = params.get('batch_size', 100)

        logger.info(
            "Sync parameters",
            extra={
                "app_id": app_id,
                "filter": filter_criteria,
                "batch_size": batch_size
            }
        )

        # Initialize clients
        onspring_client = OnspringClient()
        arrms_client = ARRMSClient()

        # Retrieve records from Onspring
        logger.info("Retrieving records from Onspring")
        records = onspring_client.get_records(
            app_id=app_id,
            filter_criteria=filter_criteria,
            page_size=batch_size
        )

        total_records = len(records)
        logger.info(f"Retrieved {total_records} records from Onspring")
        metrics.add_metric(name="RecordsRetrieved", unit=MetricUnit.Count, value=total_records)

        # Process and sync records
        sync_results = sync_records_to_arrms(
            records=records,
            arrms_client=arrms_client
        )

        # Log summary
        successful = sync_results['successful']
        failed = sync_results['failed']

        logger.info(
            "Sync completed",
            extra={
                "total": total_records,
                "successful": successful,
                "failed": failed
            }
        )

        metrics.add_metric(name="RecordsSyncedSuccessfully", unit=MetricUnit.Count, value=successful)
        metrics.add_metric(name="RecordsSyncedFailed", unit=MetricUnit.Count, value=failed)

        return build_response(
            status_code=200,
            body={
                "message": "Sync completed",
                "summary": {
                    "total_records": total_records,
                    "successful": successful,
                    "failed": failed
                },
                "errors": sync_results.get('errors', [])
            }
        )

    except ValidationError as e:
        logger.error("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="SyncValidationError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=400, body={"error": str(e)})

    except IntegrationError as e:
        logger.error("Integration error", extra={"error": str(e)})
        metrics.add_metric(name="SyncIntegrationError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=500, body={"error": "Integration error occurred"})

    except Exception as e:
        logger.exception("Unexpected error during sync")
        metrics.add_metric(name="SyncUnexpectedError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=500, body={"error": "Internal server error"})


def parse_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse event to extract parameters.

    Handles both API Gateway events and EventBridge scheduled events.

    Args:
        event: Lambda event

    Returns:
        Parsed parameters dictionary
    """
    # Check if this is an API Gateway event
    if 'body' in event:
        body = json.loads(event.get('body', '{}'))
        return body

    # Check if this is an EventBridge scheduled event
    if 'detail' in event:
        return event.get('detail', {})

    # Direct invocation or test event
    return event


@tracer.capture_method
def sync_records_to_arrms(
    records: List[Dict[str, Any]],
    arrms_client: ARRMSClient
) -> Dict[str, Any]:
    """
    Sync a batch of records to ARRMS.

    Args:
        records: List of Onspring records
        arrms_client: Initialized ARRMS client

    Returns:
        Sync results with counts and errors
    """
    successful = 0
    failed = 0
    errors = []

    for record in records:
        try:
            # Transform record
            transformed_record = transform_record(record)

            # Push to ARRMS
            arrms_client.upsert_record(transformed_record)

            successful += 1

        except Exception as e:
            failed += 1
            error_detail = {
                "record_id": record.get('recordId'),
                "error": str(e)
            }
            errors.append(error_detail)
            logger.error(
                "Failed to sync record",
                extra=error_detail
            )

    return {
        "successful": successful,
        "failed": failed,
        "errors": errors
    }


def transform_record(onspring_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform Onspring record to ARRMS format.

    This is a placeholder for data transformation logic.
    Implement specific field mappings based on your data model.

    Args:
        onspring_record: Raw record from Onspring

    Returns:
        Transformed record for ARRMS
    """
    # TODO: Implement actual transformation logic based on data models
    logger.debug("Transforming record", extra={"record_id": onspring_record.get('recordId')})

    # Placeholder transformation
    transformed = {
        "id": onspring_record.get("recordId"),
        "source": "onspring",
        "data": onspring_record,
        "synced_at": None  # Will be set by the client
    }

    return transformed
