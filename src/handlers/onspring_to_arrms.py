"""
Onspring to ARRMS Sync Handler

Retrieves data from Onspring and pushes to ARRMS.
Can be triggered via API or scheduled execution.
"""

import json
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.adapters.arrms_client import ARRMSClient
from src.adapters.onspring_client import OnspringClient
from src.utils.exceptions import IntegrationError, ValidationError
from src.utils.response_builder import build_response

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

        app_id = params.get("app_id")
        filter_criteria = params.get("filter", {})
        batch_size = params.get("batch_size", 100)

        logger.info(
            "Sync parameters",
            extra={
                "app_id": app_id,
                "filter": filter_criteria,
                "batch_size": batch_size,
            },
        )

        # Initialize clients
        onspring_client = OnspringClient()
        arrms_client = ARRMSClient()

        # Retrieve records from Onspring
        logger.info("Retrieving records from Onspring")
        records = onspring_client.get_records(app_id=app_id, filter_criteria=filter_criteria, page_size=batch_size)

        total_records = len(records)
        logger.info(f"Retrieved {total_records} records from Onspring")
        metrics.add_metric(name="RecordsRetrieved", unit=MetricUnit.Count, value=total_records)

        # Process and sync records
        sync_results = sync_records_to_arrms(records=records, arrms_client=arrms_client, onspring_client=onspring_client)

        # Log summary
        successful = sync_results["successful"]
        failed = sync_results["failed"]
        files_synced = sync_results.get("files_synced", 0)
        files_failed = sync_results.get("files_failed", 0)

        logger.info(
            "Sync completed",
            extra={
                "total": total_records,
                "successful": successful,
                "failed": failed,
                "files_synced": files_synced,
                "files_failed": files_failed,
            },
        )

        metrics.add_metric(name="RecordsSyncedSuccessfully", unit=MetricUnit.Count, value=successful)
        metrics.add_metric(name="RecordsSyncedFailed", unit=MetricUnit.Count, value=failed)
        if files_synced > 0:
            metrics.add_metric(name="FilesSynced", unit=MetricUnit.Count, value=files_synced)
        if files_failed > 0:
            metrics.add_metric(name="FilesSyncFailed", unit=MetricUnit.Count, value=files_failed)

        return build_response(
            status_code=200,
            body={
                "message": "Sync completed",
                "summary": {
                    "total_records": total_records,
                    "successful": successful,
                    "failed": failed,
                    "files_synced": files_synced,
                    "files_failed": files_failed,
                },
                "errors": sync_results.get("errors", []),
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
    Parse event to extract parameters.

    Handles both API Gateway events and EventBridge scheduled events.

    Args:
        event: Lambda event

    Returns:
        Parsed parameters dictionary
    """
    # Check if this is an API Gateway event
    if "body" in event:
        body = json.loads(event.get("body", "{}"))
        return body

    # Check if this is an EventBridge scheduled event
    if "detail" in event:
        return event.get("detail", {})

    # Direct invocation or test event
    return event


@tracer.capture_method
def sync_records_to_arrms(
    records: List[Dict[str, Any]],
    arrms_client: ARRMSClient,
    onspring_client: OnspringClient,
) -> Dict[str, Any]:
    """
    Sync a batch of records to ARRMS including file attachments.

    Args:
        records: List of Onspring records
        arrms_client: Initialized ARRMS client
        onspring_client: Initialized Onspring client for file downloads

    Returns:
        Sync results with counts and errors
    """
    successful = 0
    failed = 0
    errors = []
    files_synced = 0
    files_failed = 0

    for record in records:
        try:
            # Transform record to extract metadata
            transformed_record = transform_record(record)
            onspring_record_id = str(record.get("recordId"))

            # Get all files from Onspring attachments field
            files = onspring_client.get_record_files(record)

            if not files or len(files) == 0:
                logger.warning(f"No files found for record {onspring_record_id}, skipping")
                failed += 1
                errors.append(
                    {
                        "record_id": onspring_record_id,
                        "error": "No files found in record",
                    }
                )
                continue

            # Use the first file as the questionnaire file
            # All remaining files are treated as additional attachments
            questionnaire_file = files[0]
            additional_files = files[1:] if len(files) > 1 else []

            logger.info(
                f"Processing {len(files)} total files for record {onspring_record_id}: "
                f"1 questionnaire, {len(additional_files)} additional attachments"
            )

            # Download questionnaire file from Onspring
            try:
                file_content = onspring_client.download_file(
                    record_id=questionnaire_file["record_id"],
                    field_id=questionnaire_file["field_id"],
                    file_id=questionnaire_file["file_id"],
                )

                # Get file extension from original filename (Excel, Word, or PDF)
                file_name = questionnaire_file.get("file_name")
                if not file_name:
                    raise ValidationError(
                        f"Questionnaire file for record {onspring_record_id} is missing filename in Onspring data"
                    )

                _, file_ext = os.path.splitext(file_name)
                if not file_ext:
                    raise ValidationError(
                        f"Questionnaire file '{file_name}' for record {onspring_record_id} has no file extension"
                    )

                # Save to temporary file for upload
                with tempfile.NamedTemporaryFile(mode="wb", suffix=file_ext, delete=False) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name

                # Upload questionnaire to ARRMS with external tracking
                result = arrms_client.upload_questionnaire(
                    file_path=temp_file_path,
                    external_id=onspring_record_id,
                    external_source="onspring",
                    external_metadata=transformed_record.get("external_metadata", {}),
                    # Additional form fields from transformed record
                    requester_name=transformed_record.get("requester_name"),
                    urgency=transformed_record.get("urgency"),
                    assessment_type=transformed_record.get("assessment_type"),
                    due_date=transformed_record.get("due_date"),
                    notes=transformed_record.get("notes") or transformed_record.get("description"),
                )

                # Clean up temp file
                os.unlink(temp_file_path)

                arrms_questionnaire_id = result.get("id")

                # Verify external reference was created
                external_ref = arrms_client.parse_external_reference(result, "onspring")
                if external_ref:
                    logger.info(
                        f"Synced Onspring record {onspring_record_id} to ARRMS {arrms_questionnaire_id}",
                        extra={
                            "external_reference_id": external_ref["id"],
                            "external_id": external_ref["external_id"],
                        },
                    )
                else:
                    logger.warning(f"External reference not found in response for {onspring_record_id}")

            except Exception as upload_error:
                logger.error(
                    f"Failed to upload questionnaire for record {onspring_record_id}",
                    extra={"error": str(upload_error)},
                )
                raise

            # Process additional file attachments
            if additional_files:
                for file_info in additional_files:
                    try:
                        # Download file from Onspring
                        file_content = onspring_client.download_file(
                            record_id=file_info["record_id"],
                            field_id=file_info["field_id"],
                            file_id=file_info["file_id"],
                        )

                        # Upload to ARRMS with external metadata
                        arrms_client.upload_document(
                            questionnaire_id=arrms_questionnaire_id,
                            file_content=file_content,
                            file_name=file_info["file_name"],
                            content_type=file_info["content_type"],
                            external_id=str(file_info["file_id"]),  # Onspring file ID
                            source_metadata={
                                "onspring_record_id": record.get("recordId"),
                                "onspring_field_id": file_info["field_id"],
                                "onspring_file_id": file_info["file_id"],
                                "notes": file_info.get("notes"),
                                "uploaded_at": datetime.utcnow().isoformat(),
                            },
                        )

                        files_synced += 1
                        logger.debug(f"Synced supporting file: {file_info['file_name']}")

                    except Exception as file_error:
                        files_failed += 1
                        logger.error(
                            f"Failed to sync file {file_info.get('file_name')}",
                            extra={
                                "error": str(file_error),
                                "file_info": file_info,
                            },
                        )

            successful += 1

        except Exception as e:
            failed += 1
            error_detail = {"record_id": record.get("recordId"), "error": str(e)}
            errors.append(error_detail)
            logger.error("Failed to sync record", extra=error_detail)

    return {
        "successful": successful,
        "failed": failed,
        "errors": errors,
        "files_synced": files_synced,
        "files_failed": files_failed,
    }


def transform_record(onspring_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform Onspring questionnaire record to ARRMS format.

    Onspring Structure:
    {
        "recordId": 12345,
        "appId": 100,
        "fields": {
            "Title": {"value": "SOC 2 Assessment", "fieldId": 101},
            "Client": {"value": "Integrity Risk", "fieldId": 102},
            "DueDate": {"value": "2025-03-31", "fieldId": 103},
            "Status": {"value": "New", "fieldId": 104},
            "Description": {"value": "Annual assessment", "fieldId": 105}
        }
    }

    Args:
        onspring_record: Raw record from Onspring

    Returns:
        Transformed record for ARRMS with external system tracking
    """
    from datetime import datetime

    logger.debug("Transforming record", extra={"record_id": onspring_record.get("recordId")})

    fields = onspring_record.get("fields", {})

    # Helper to extract field value
    def get_field_value(field_name: str, default=None):
        field_data = fields.get(field_name, {})
        return field_data.get("value", default)

    # Transform to ARRMS format
    transformed = {
        # ARRMS core fields
        "title": get_field_value("Title", "Untitled Questionnaire"),
        "client_name": get_field_value("Client"),
        "description": get_field_value("Description"),
        "due_date": get_field_value("DueDate"),  # Assumes ISO format
        # External system tracking
        "external_id": str(onspring_record.get("recordId")),
        "external_source": "onspring",
        "external_metadata": {
            "app_id": onspring_record.get("appId"),
            "onspring_status": get_field_value("Status"),
            "onspring_url": f"https://app.onspring.com/record/{onspring_record.get('recordId')}",
            "field_ids": {
                "title": fields.get("Title", {}).get("fieldId"),
                "client": fields.get("Client", {}).get("fieldId"),
                "due_date": fields.get("DueDate", {}).get("fieldId"),
                "status": fields.get("Status", {}).get("fieldId"),
                "description": fields.get("Description", {}).get("fieldId"),
            },
            "synced_at": datetime.utcnow().isoformat(),
            "sync_type": "webhook",  # or "scheduled"
        },
    }

    logger.debug(
        "Transformed Onspring record",
        extra={
            "onspring_id": onspring_record.get("recordId"),
            "arrms_title": transformed["title"],
        },
    )

    return transformed
