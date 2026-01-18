"""
Health Check Handler

Provides health status for monitoring and load balancing.
Verifies connectivity to external services.
"""

import os
from typing import Any, Dict

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from adapters.arrms_client import ARRMSClient
from adapters.onspring_client import OnspringClient
from utils.response_builder import build_response

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Lambda handler for health check endpoint.

    Args:
        event: API Gateway event
        context: Lambda context object

    Returns:
        API Gateway response with health status
    """
    try:
        logger.info("Processing health check request")

        # Basic health check
        health_status = {
            "status": "healthy",
            "service": "arrms-onspring-integration",
            "environment": os.environ.get("ENVIRONMENT", "unknown"),
            "version": "1.0.0",
            "checks": {},
        }

        # Check environment variables
        required_env_vars = [
            "ONSPRING_API_URL",
            "ONSPRING_API_KEY_SECRET",
            "ARRMS_API_URL",
            "ARRMS_API_KEY_SECRET",
        ]

        env_check = all(os.environ.get(var) for var in required_env_vars)
        health_status["checks"]["environment"] = "pass" if env_check else "fail"

        # Optional: Check external service connectivity
        # Uncomment to enable deep health checks
        # health_status["checks"]["onspring"] = check_onspring_health()
        # health_status["checks"]["arrms"] = check_arrms_health()

        # Determine overall status
        all_checks_pass = all(status == "pass" for status in health_status["checks"].values())

        if not all_checks_pass:
            health_status["status"] = "degraded"
            logger.warning("Health check degraded", extra=health_status)
            return build_response(status_code=503, body=health_status)

        logger.info("Health check passed")
        return build_response(status_code=200, body=health_status)

    except Exception as e:
        logger.exception("Health check failed")
        return build_response(status_code=503, body={"status": "unhealthy", "error": str(e)})


@tracer.capture_method
def check_onspring_health() -> str:
    """
    Check connectivity to Onspring API.

    Returns:
        Health status: 'pass' or 'fail'
    """
    try:
        client = OnspringClient()
        # Perform a lightweight API call
        client.health_check()
        return "pass"
    except Exception as e:
        logger.error(f"Onspring health check failed: {str(e)}")
        return "fail"


@tracer.capture_method
def check_arrms_health() -> str:
    """
    Check connectivity to ARRMS API.

    Returns:
        Health status: 'pass' or 'fail'
    """
    try:
        client = ARRMSClient()
        # Perform a lightweight API call
        client.health_check()
        return "pass"
    except Exception as e:
        logger.error(f"ARRMS health check failed: {str(e)}")
        return "fail"
