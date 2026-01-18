"""
Onspring Webhook Handler

Receives and processes webhook events from Onspring.
This handler acts as the entry point for event-driven integration.
"""

import json
import os
import tempfile
from datetime import datetime
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
        body = json.loads(event.get("body", "[]"))
        logger.info("Webhook payload", extra={"payload": body})

        # Onspring REST API Outcome sends array like: [{"RecordId": "16", "AppId": "100"}]
        if not isinstance(body, list) or len(body) == 0:
            raise ValidationError("Expected non-empty array of records")

        # Extract first record (Onspring typically sends one record per trigger)
        record = body[0]
        record_id = record.get("RecordId")
        app_id = record.get("AppId")

        if not record_id:
            raise ValidationError("Missing required field: RecordId")

        # Convert to integer
        try:
            record_id = int(record_id)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid RecordId format: {record_id}")

        # Get appId from body (Onspring should send it in the webhook payload)
        if not app_id:
            # Try to get from environment variable as fallback
            app_id = os.environ.get("ONSPRING_DEFAULT_APP_ID")

        if not app_id:
            raise ValidationError("Missing AppId - ensure Onspring webhook includes AppId in body")

        try:
            app_id = int(app_id)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid AppId format: {app_id}")

        logger.info(
            "Processing webhook", extra={"record_id": record_id, "app_id": app_id}
        )

        # Add metric for webhook received
        metrics.add_metric(name="WebhookReceived", unit=MetricUnit.Count, value=1)

        # Initialize clients
        onspring_client = OnspringClient()
        arrms_client = ARRMSClient()

        # Fetch full record from Onspring
        logger.info(f"Fetching record {record_id} from Onspring app {app_id}")
        record_data = onspring_client.get_record(app_id=app_id, record_id=record_id)

        # Transform data to extract metadata
        from handlers.onspring_to_arrms import transform_record
        transformed_data = transform_record(record_data)
        onspring_record_id = str(record_id)

        # Get all files from Onspring attachments field
        files = onspring_client.get_record_files(record_data)

        if not files or len(files) == 0:
            raise ValidationError(
                f"No files found for record {onspring_record_id}"
            )

        # Use the first file as the questionnaire file
        # All remaining files are treated as additional attachments
        questionnaire_file = files[0]
        additional_files = files[1:] if len(files) > 1 else []

        logger.info(
            f"Processing {len(files)} total files: 1 questionnaire, {len(additional_files)} additional attachments"
        )

        # Download questionnaire file from Onspring
        file_content = onspring_client.download_file(
            record_id=questionnaire_file["record_id"],
            field_id=questionnaire_file["field_id"],
            file_id=questionnaire_file["file_id"],
        )

        # Get file extension from original filename
        import os as os_path
        file_name = questionnaire_file.get("file_name")
        if not file_name:
            raise ValidationError(
                f"Questionnaire file is missing filename in Onspring data"
            )

        _, file_ext = os_path.splitext(file_name)
        if not file_ext:
            raise ValidationError(
                f"Questionnaire file '{file_name}' has no file extension"
            )

        # Save to temporary file for upload
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=file_ext, delete=False
        ) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        try:
            # Upload questionnaire to ARRMS with external tracking
            result = arrms_client.upload_questionnaire(
                file_path=temp_file_path,
                external_id=onspring_record_id,
                external_source="onspring",
                external_metadata=transformed_data.get("external_metadata", {}),
                # Additional form fields from transformed record
                requester_name=transformed_data.get("requester_name"),
                urgency=transformed_data.get("urgency"),
                assessment_type=transformed_data.get("assessment_type"),
                due_date=transformed_data.get("due_date"),
                notes=transformed_data.get("notes")
                or transformed_data.get("description"),
            )
        finally:
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
            logger.warning(
                f"External reference not found in response for {onspring_record_id}"
            )

        # Process additional file attachments
        files_synced = 0
        files_failed = 0

        if additional_files:
            logger.info(f"Processing {len(additional_files)} additional file attachments")

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
                            "onspring_record_id": record_id,
                            "onspring_field_id": file_info["field_id"],
                            "onspring_file_id": file_info["file_id"],
                            "notes": file_info.get("notes"),
                            "uploaded_at": datetime.utcnow().isoformat(),
                        },
                    )

                    files_synced += 1
                    logger.info(f"Synced supporting file: {file_info['file_name']}")

                except Exception as file_error:
                    files_failed += 1
                    logger.error(
                        f"Failed to sync file {file_info.get('file_name')}",
                        extra={"error": str(file_error), "file_info": file_info},
                    )

            # Add file sync metrics
            if files_synced > 0:
                metrics.add_metric(
                    name="FilesSynced", unit=MetricUnit.Count, value=files_synced
                )
            if files_failed > 0:
                metrics.add_metric(
                    name="FilesSyncFailed", unit=MetricUnit.Count, value=files_failed
                )

        # Add success metric
        metrics.add_metric(name="WebhookProcessed", unit=MetricUnit.Count, value=1)

        logger.info(
            "Successfully processed webhook",
            extra={
                "arrms_questionnaire_id": arrms_questionnaire_id,
                "files_synced": files_synced,
                "files_failed": files_failed,
            },
        )

        return build_response(
            status_code=200,
            body={
                "message": "Webhook processed successfully",
                "recordId": record_id,
                "appId": app_id,
                "arrmsSynced": True,
                "filesSynced": files_synced,
                "filesFailed": files_failed,
            },
        )

    except ValidationError as e:
        logger.error("Validation error", extra={"error": str(e)})
        metrics.add_metric(
            name="WebhookValidationError", unit=MetricUnit.Count, value=1
        )
        return build_response(status_code=400, body={"error": str(e)})

    except IntegrationError as e:
        logger.error("Integration error", extra={"error": str(e)})
        metrics.add_metric(
            name="WebhookIntegrationError", unit=MetricUnit.Count, value=1
        )
        return build_response(
            status_code=500, body={"error": "Integration error occurred"}
        )

    except Exception as e:
        logger.exception("Unexpected error processing webhook")
        metrics.add_metric(
            name="WebhookUnexpectedError", unit=MetricUnit.Count, value=1
        )
        return build_response(status_code=500, body={"error": "Internal server error"})
