"""
Onspring Webhook Handler

Receives and processes webhook events from Onspring.
This handler acts as the entry point for event-driven integration.
"""

import json
from typing import Dict, Any
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
    Lambda handler for processing Onspring webhook events.

    Args:
        event: API Gateway event containing webhook payload
        context: Lambda context object

    Returns:
        API Gateway response with status code and body
    """
    try:
        logger.info("Received Onspring webhook event")

        # Parse request body (Onspring sends an array of records)
        body = json.loads(event.get('body', '[]'))
        logger.info("Webhook payload", extra={"payload": body})

        # Onspring REST API Outcome sends array like: [{"RecordId": "16"}]
        if not isinstance(body, list) or len(body) == 0:
            raise ValidationError("Expected non-empty array of records")

        # Extract first record (Onspring typically sends one record per trigger)
        record = body[0]
        record_id = record.get('RecordId')

        if not record_id:
            raise ValidationError("Missing required field: RecordId")

        # Convert to integer
        try:
            record_id = int(record_id)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid RecordId format: {record_id}")

        # Get appId from query string parameters or environment variable
        # This should be configured in the Onspring REST API Outcome URL
        query_params = event.get('queryStringParameters') or {}
        app_id = query_params.get('appId')

        if not app_id:
            # Try to get from environment variable as fallback
            import os
            app_id = os.environ.get('ONSPRING_DEFAULT_APP_ID')

        if not app_id:
            raise ValidationError("Missing appId - include ?appId=XXX in webhook URL")

        try:
            app_id = int(app_id)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid appId format: {app_id}")

        logger.info(
            "Processing webhook",
            extra={
                "record_id": record_id,
                "app_id": app_id
            }
        )

        # Add metric for webhook received
        metrics.add_metric(name="WebhookReceived", unit=MetricUnit.Count, value=1)

        # Initialize clients
        onspring_client = OnspringClient()
        arrms_client = ARRMSClient()

        # Fetch full record from Onspring
        logger.info(f"Fetching record {record_id} from Onspring app {app_id}")
        record_data = onspring_client.get_record(app_id=app_id, record_id=record_id)

        # Transform data for ARRMS
        transformed_data = transform_onspring_to_arrms(record_data)

        # Push to ARRMS (upsert - create or update)
        result = arrms_client.upsert_record(transformed_data)

        # Add success metric
        metrics.add_metric(name="WebhookProcessed", unit=MetricUnit.Count, value=1)

        logger.info("Successfully processed webhook", extra={"result": result})

        return build_response(
            status_code=200,
            body={
                "message": "Webhook processed successfully",
                "recordId": record_id,
                "appId": app_id,
                "arrmsSynced": True
            }
        )

    except ValidationError as e:
        logger.error("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="WebhookValidationError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=400, body={"error": str(e)})

    except IntegrationError as e:
        logger.error("Integration error", extra={"error": str(e)})
        metrics.add_metric(name="WebhookIntegrationError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=500, body={"error": "Integration error occurred"})

    except Exception as e:
        logger.exception("Unexpected error processing webhook")
        metrics.add_metric(name="WebhookUnexpectedError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=500, body={"error": "Internal server error"})


@tracer.capture_method
def process_webhook_event(
    event_type: str,
    record_id: int,
    app_id: int,
    body: Dict[str, Any],
    onspring_client: OnspringClient,
    arrms_client: ARRMSClient
) -> Dict[str, Any]:
    """
    Process webhook event based on event type.

    Args:
        event_type: Type of webhook event (e.g., 'RecordCreated', 'RecordUpdated')
        record_id: Onspring record ID
        app_id: Onspring application ID
        body: Complete webhook payload
        onspring_client: Initialized Onspring client
        arrms_client: Initialized ARRMS client

    Returns:
        Processing result dictionary
    """
    logger.info(f"Processing event type: {event_type}")

    # Handle different event types
    if event_type in ['RecordCreated', 'RecordUpdated']:
        # Retrieve full record data from Onspring
        record_data = onspring_client.get_record(app_id=app_id, record_id=record_id)

        # Transform data for ARRMS
        transformed_data = transform_onspring_to_arrms(record_data)

        # Push to ARRMS
        if event_type == 'RecordCreated':
            result = arrms_client.create_record(transformed_data)
        else:
            result = arrms_client.update_record(transformed_data)

        return result

    elif event_type == 'RecordDeleted':
        # Handle record deletion
        result = arrms_client.delete_record(record_id=record_id)
        return result

    else:
        logger.warning(f"Unhandled event type: {event_type}")
        return {"status": "ignored", "reason": f"Event type {event_type} not supported"}


def transform_onspring_to_arrms(onspring_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform Onspring record data to ARRMS format.

    This is a placeholder for data transformation logic.
    Implement specific field mappings based on your data model.

    Args:
        onspring_data: Raw data from Onspring

    Returns:
        Transformed data for ARRMS
    """
    # TODO: Implement actual transformation logic based on data models
    logger.info("Transforming Onspring data to ARRMS format")

    # Placeholder transformation
    transformed = {
        "id": onspring_data.get("recordId"),
        "source": "onspring",
        "data": onspring_data
    }

    return transformed
