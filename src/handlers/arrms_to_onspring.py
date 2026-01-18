"""
ARRMS to Onspring Sync Handler

Syncs questionnaire progress data from ARRMS back to Onspring.
Updates Onspring fields with question counts, confidence distribution, and status.

This handler can be triggered by:
- ARRMS webhook notifications (future - when webhooks are implemented)
- API Gateway endpoint (manual trigger)
- EventBridge schedule (periodic polling)
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from adapters.arrms_client import ARRMSClient
from adapters.onspring_client import OnspringClient
from utils.exceptions import IntegrationError, ValidationError
from utils.response_builder import build_response

logger = Logger()
tracer = Tracer()
metrics = Metrics()


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Lambda handler for syncing ARRMS questionnaire data to Onspring.

    Event formats supported:
    1. ARRMS Webhook (future):
       {
         "event_type": "questionnaire.response_approved",
         "external_id": "onspring-12345",
         "external_source": "onspring"
       }

    2. API Gateway / Manual trigger:
       {
         "external_id": "onspring-12345",
         "force_sync": true
       }

    3. EventBridge scheduled event:
       {
         "source": "aws.events",
         "detail": {
           "external_ids": ["onspring-123", "onspring-456"]
         }
       }

    Args:
        event: Event payload (varies by trigger source)
        context: Lambda context object

    Returns:
        API Gateway response or EventBridge result
    """
    try:
        logger.info("Starting ARRMS to Onspring sync")

        # Parse event to extract parameters
        params = parse_event(event)
        external_ids = params.get("external_ids", [])
        force_sync = params.get("force_sync", False)

        if not external_ids:
            raise ValidationError("No external_ids provided for sync")

        logger.info(
            "Sync parameters",
            extra={"external_ids": external_ids, "force_sync": force_sync, "count": len(external_ids)},
        )

        # Initialize clients
        arrms_client = ARRMSClient()
        onspring_client = OnspringClient()

        # Process each external_id
        results = []
        for external_id in external_ids:
            try:
                result = sync_questionnaire_to_onspring(
                    external_id=external_id,
                    arrms_client=arrms_client,
                    onspring_client=onspring_client,
                    force_sync=force_sync,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to sync {external_id}", extra={"error": str(e)})
                results.append(
                    {
                        "external_id": external_id,
                        "success": False,
                        "error": str(e),
                    }
                )

        # Calculate summary
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful

        logger.info(
            "Sync completed",
            extra={"total": len(results), "successful": successful, "failed": failed},
        )

        metrics.add_metric(name="QuestionnaireSyncSuccessful", unit=MetricUnit.Count, value=successful)
        metrics.add_metric(name="QuestionnaireSyncFailed", unit=MetricUnit.Count, value=failed)

        return build_response(
            status_code=200,
            body={
                "message": "ARRMS to Onspring sync completed",
                "summary": {
                    "total": len(results),
                    "successful": successful,
                    "failed": failed,
                },
                "results": results,
            },
        )

    except ValidationError as e:
        logger.error("Validation error", extra={"error": str(e)})
        metrics.add_metric(name="SyncValidationError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=400, body={"error": str(e)})

    except IntegrationError as e:
        logger.error("Integration error", extra={"error": str(e)})
        metrics.add_metric(name="SyncIntegrationError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=500, body={"error": "Integration error occurred"})

    except Exception:
        logger.exception("Unexpected error during sync")
        metrics.add_metric(name="SyncUnexpectedError", unit=MetricUnit.Count, value=1)
        return build_response(status_code=500, body={"error": "Internal server error"})


def parse_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse event to extract sync parameters.

    Handles multiple event formats:
    - ARRMS webhook
    - API Gateway request
    - EventBridge scheduled event
    - Direct invocation

    Args:
        event: Lambda event

    Returns:
        Parsed parameters with external_ids and options
    """
    # Check if this is an API Gateway event
    if "body" in event:
        body = json.loads(event.get("body", "{}"))
        external_id = body.get("external_id")
        external_ids = body.get("external_ids", [external_id] if external_id else [])
        force_sync = body.get("force_sync", False)

        return {"external_ids": external_ids, "force_sync": force_sync}

    # Check if this is an EventBridge scheduled event
    if event.get("source") == "aws.events" and "detail" in event:
        detail = event.get("detail", {})
        external_ids = detail.get("external_ids", [])
        return {"external_ids": external_ids, "force_sync": False}

    # Check if this is an ARRMS webhook (future)
    if "event_type" in event and event.get("event_type", "").startswith("questionnaire."):
        external_id = event.get("external_id")
        return {"external_ids": [external_id] if external_id else [], "force_sync": False}

    # Direct invocation or test event
    external_id = event.get("external_id")
    external_ids = event.get("external_ids", [external_id] if external_id else [])
    force_sync = event.get("force_sync", False)

    return {"external_ids": external_ids, "force_sync": force_sync}


@tracer.capture_method
def sync_questionnaire_to_onspring(
    external_id: str,
    arrms_client: ARRMSClient,
    onspring_client: OnspringClient,
    force_sync: bool = False,
) -> Dict[str, Any]:
    """
    Sync a single questionnaire from ARRMS to Onspring.

    Workflow:
    1. Fetch statistics from ARRMS
    2. Calculate Onspring field values
    3. Update Onspring record

    Args:
        external_id: Onspring record ID (e.g., "onspring-12345" or "12345")
        arrms_client: Initialized ARRMS client
        onspring_client: Initialized Onspring client
        force_sync: Force sync even if data hasn't changed

    Returns:
        Sync result with success status and updated fields

    Raises:
        IntegrationError: If sync fails
    """
    logger.info(f"Syncing questionnaire {external_id} from ARRMS to Onspring")

    try:
        # Fetch statistics from ARRMS
        arrms_stats = fetch_arrms_statistics(
            external_id=external_id,
            arrms_client=arrms_client,
        )

        if not arrms_stats:
            raise IntegrationError(f"Could not fetch statistics for {external_id}")

        # Calculate Onspring field values
        field_values = calculate_onspring_fields(arrms_stats)

        logger.info(
            f"Calculated field values for {external_id}",
            extra={"field_values": field_values},
        )

        # Extract Onspring record ID
        onspring_record_id = extract_onspring_record_id(external_id)

        # Update Onspring record
        update_onspring_record(
            record_id=onspring_record_id,
            field_values=field_values,
            onspring_client=onspring_client,
        )

        logger.info(f"Successfully synced {external_id} to Onspring record {onspring_record_id}")

        return {
            "external_id": external_id,
            "onspring_record_id": onspring_record_id,
            "success": True,
            "fields_updated": list(field_values.keys()),
            "arrms_status": arrms_stats.get("summary", {}).get("approved_questions"),
            "onspring_status": field_values.get("Status"),
        }

    except Exception as e:
        logger.error(
            f"Failed to sync questionnaire {external_id}",
            extra={"error": str(e)},
        )
        raise IntegrationError(f"Sync failed for {external_id}: {str(e)}")


def fetch_arrms_statistics(
    external_id: str,
    arrms_client: ARRMSClient,
) -> Optional[Dict[str, Any]]:
    """
    Fetch questionnaire statistics from ARRMS.

    Uses the /api/v1/integrations/questionnaires/{external_id}/statistics endpoint.

    Args:
        external_id: External system ID
        arrms_client: ARRMS client instance

    Returns:
        Statistics data from ARRMS or None if not found
    """
    try:
        # Use existing method if available, otherwise add new method
        stats = arrms_client.get_questionnaire_statistics(
            external_id=external_id,
            external_source="onspring",
        )

        logger.debug(
            f"Fetched ARRMS statistics for {external_id}",
            extra={"stats": stats},
        )

        return stats

    except Exception as e:
        logger.error(
            f"Error fetching ARRMS statistics for {external_id}",
            extra={"error": str(e)},
        )
        return None


def calculate_onspring_fields(arrms_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform ARRMS statistics into Onspring field values.

    Maps ARRMS data to Onspring fields per lambda-onspring-sync.md spec:
    - Question counts (total, complete, open)
    - Confidence distribution (very_high, high, medium, low)
    - Status calculation (Not Started, Request in Process, Ready for Validation)

    Args:
        arrms_stats: ARRMS statistics response

    Returns:
        Dictionary mapping Onspring field names to values
    """
    summary = arrms_stats.get("summary", {})
    confidence_dist = summary.get("confidence_distribution", {})
    metadata = arrms_stats.get("metadata", {})

    # Calculate status
    onspring_status = calculate_onspring_status(
        total_questions=summary.get("total_questions", 0),
        answered_questions=summary.get("answered_questions", 0),
        approved_questions=summary.get("approved_questions", 0),
        document_url=get_document_url(metadata),
    )

    # Map to Onspring field names
    # NOTE: These field names should match Onspring app configuration
    field_values = {
        # Question counts
        "Total Assessment Questions": summary.get("total_questions", 0),
        "Complete Assessment Questions": summary.get("approved_questions", 0),
        "Open Assessment Questions": summary.get("unanswered_questions", 0),
        # Confidence distribution
        # Map ARRMS confidence levels to Onspring fields
        "High Confidence Questions": confidence_dist.get("very_high", 0),  # >= 0.90
        "Medium-High Confidence": confidence_dist.get("high", 0),  # 0.70-0.90
        "Medium-Low Confidence": confidence_dist.get("medium", 0),  # 0.50-0.70
        "Low Confidence Questions": confidence_dist.get("low", 0),  # < 0.50
        # Status
        "Status": onspring_status,
    }

    return field_values


def calculate_onspring_status(
    total_questions: int,
    answered_questions: int,
    approved_questions: int,
    document_url: Optional[str],
) -> str:
    """
    Calculate Onspring status from ARRMS completion data.

    Status values (per lambda-onspring-sync.md):
    1. "Not Started" - No responses generated yet
    2. "Request in Process" - Has responses but not all approved or no document
    3. "Ready for Validation" - All questions approved AND document uploaded

    Args:
        total_questions: Total number of questions
        answered_questions: Number of questions with responses
        approved_questions: Number of approved responses
        document_url: URL of output document (if available)

    Returns:
        Onspring status string
    """
    has_responses = answered_questions > 0
    all_approved = approved_questions == total_questions
    has_document = document_url is not None

    if not has_responses:
        return "Not Started"

    if all_approved and has_document:
        return "Ready for Validation"

    return "Request in Process"


def get_document_url(metadata: Dict[str, Any]) -> Optional[str]:
    """
    Extract document URL from ARRMS metadata.

    Args:
        metadata: ARRMS metadata object

    Returns:
        Document URL or None
    """
    source_doc = metadata.get("source_document")
    if source_doc:
        return source_doc.get("url")
    return None


def extract_onspring_record_id(external_id: str) -> int:
    """
    Extract Onspring record ID from external_id.

    External ID formats:
    - "onspring-12345" -> 12345
    - "12345" -> 12345

    Args:
        external_id: External system ID

    Returns:
        Onspring record ID as integer

    Raises:
        ValidationError: If external_id format is invalid
    """
    # Remove "onspring-" prefix if present
    if external_id.startswith("onspring-"):
        record_id_str = external_id.replace("onspring-", "")
    else:
        record_id_str = external_id

    try:
        return int(record_id_str)
    except ValueError:
        raise ValidationError(f"Invalid external_id format: {external_id}")


def update_onspring_record(
    record_id: int,
    field_values: Dict[str, Any],
    onspring_client: OnspringClient,
) -> None:
    """
    Update Onspring record fields with calculated values.

    Args:
        record_id: Onspring record ID
        field_values: Dictionary of field names to values
        onspring_client: Onspring client instance

    Raises:
        IntegrationError: If update fails
    """
    logger.info(
        f"Updating Onspring record {record_id}",
        extra={"field_count": len(field_values)},
    )

    try:
        # Get app_id from environment
        app_id = int(os.environ.get("ONSPRING_DEFAULT_APP_ID", "0"))
        if not app_id:
            raise ValidationError("ONSPRING_DEFAULT_APP_ID not configured")

        # Get field ID mappings from environment
        # Format: {"Field Name": field_id, ...}
        field_mapping_json = os.environ.get("ONSPRING_FIELD_MAPPING", "{}")
        field_mapping = json.loads(field_mapping_json)

        # Update each field
        for field_name, value in field_values.items():
            field_id = field_mapping.get(field_name)

            if not field_id:
                logger.warning(
                    f"No field mapping found for '{field_name}', skipping",
                    extra={"field_name": field_name},
                )
                continue

            # Update field in Onspring
            onspring_client.update_field_value(
                app_id=app_id,
                record_id=record_id,
                field_id=field_id,
                value=value,
            )

            logger.debug(
                f"Updated field '{field_name}' (ID: {field_id}) with value: {value}",
                extra={"field_name": field_name, "field_id": field_id, "value": value},
            )

        logger.info(f"Successfully updated Onspring record {record_id}")

    except json.JSONDecodeError as e:
        raise IntegrationError(f"Invalid ONSPRING_FIELD_MAPPING JSON: {str(e)}")
    except Exception as e:
        raise IntegrationError(f"Failed to update Onspring record {record_id}: {str(e)}")
