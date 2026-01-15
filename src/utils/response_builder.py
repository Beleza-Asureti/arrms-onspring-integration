"""
Response Builder Utility

Provides consistent API Gateway response formatting.
"""

import json
from typing import Dict, Any, Optional


def build_response(
    status_code: int, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Build standardized API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body dictionary
        headers: Optional additional headers

    Returns:
        API Gateway response dictionary
    """
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }

    if headers:
        default_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body, default=str),
    }


def build_error_response(
    status_code: int,
    error_message: str,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build standardized error response.

    Args:
        status_code: HTTP status code
        error_message: Human-readable error message
        error_code: Machine-readable error code
        details: Additional error details

    Returns:
        API Gateway error response dictionary
    """
    error_body = {
        "error": {
            "message": error_message,
            "code": error_code or f"ERROR_{status_code}",
        }
    }

    if details:
        error_body["error"]["details"] = details

    return build_response(status_code, error_body)


def build_success_response(
    data: Any, message: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build standardized success response.

    Args:
        data: Response data
        message: Optional success message
        metadata: Optional metadata

    Returns:
        API Gateway success response dictionary
    """
    response_body = {"success": True, "data": data}

    if message:
        response_body["message"] = message

    if metadata:
        response_body["metadata"] = metadata

    return build_response(200, response_body)
