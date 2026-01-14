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

        # Parse request body
        body = json.loads(event.get('body', '{}'))
        logger.info("Webhook payload", extra={"payload": body})

        # Extract event metadata
        event_type = body.get('eventType')
        record_id = body.get('recordId')
        app_id = body.get('appId')

        if not event_type or not record_id:
            raise ValidationError("Missing required fields: eventType or recordId")

        logger.info(
            "Processing webhook",
            extra={
                "event_type": event_type,
                "record_id": record_id,
                "app_id": app_id
            }
        )

        # Add metric for webhook received
        metrics.add_metric(name="WebhookReceived", unit=MetricUnit.Count, value=1)
        metrics.add_metadata(key="event_type", value=event_type)

        # Initialize clients
        onspring_client = OnspringClient()
        arrms_client = ARRMSClient()

        # Process based on event type
        result = process_webhook_event(
            event_type=event_type,
            record_id=record_id,
            app_id=app_id,
            body=body,
            onspring_client=onspring_client,
            arrms_client=arrms_client
        )

        # Add success metric
        metrics.add_metric(name="WebhookProcessed", unit=MetricUnit.Count, value=1)

        logger.info("Successfully processed webhook", extra={"result": result})

        return build_response(
            status_code=200,
            body={
                "message": "Webhook processed successfully",
                "recordId": record_id,
                "eventType": event_type
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
