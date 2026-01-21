#!/usr/bin/env python3
"""
Local Integration Test Harness

Runs the actual integration handler code against mock/local services.
This allows testing the full integration flow without AWS or production services.

Usage:
    # Start mock Onspring server in one terminal:
    python scripts/mock_onspring_server.py

    # Run integration test in another terminal:
    python scripts/local_integration_test.py

    # Or run with real ARRMS (requires ARRMS_API_KEY env var):
    python scripts/local_integration_test.py --real-arrms

Environment Variables:
    ONSPRING_API_URL      - URL of Onspring API (default: http://localhost:5001)
    ONSPRING_API_KEY      - Onspring API key (for local: any value works)
    ARRMS_API_URL         - URL of ARRMS API
    ARRMS_API_KEY         - ARRMS API key
    LOCAL_DEV             - Set to 'true' to use local secrets provider
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Optional

# Add stubs directory FIRST to override aws_lambda_powertools with local stubs
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs"))
# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# Set environment before imports
os.environ.setdefault("LOCAL_DEV", "true")
os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "arrms-integration-local")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


def setup_environment(
    onspring_url: str = "http://localhost:5001",
    arrms_url: Optional[str] = None,
    onspring_api_key: str = "local-test-key",
    arrms_api_key: Optional[str] = None,
):
    """
    Configure environment for local testing.

    Args:
        onspring_url: URL of Onspring API (mock server)
        arrms_url: URL of ARRMS API (real or mock)
        onspring_api_key: Onspring API key
        arrms_api_key: ARRMS API key
    """
    os.environ["LOCAL_DEV"] = "true"
    os.environ["ONSPRING_API_URL"] = onspring_url
    os.environ["ONSPRING_API_KEY_SECRET"] = "onspring-api-key"
    os.environ["ONSPRING_API_KEY"] = onspring_api_key

    if arrms_url:
        os.environ["ARRMS_API_URL"] = arrms_url
    if arrms_api_key:
        os.environ["ARRMS_API_KEY"] = arrms_api_key

    os.environ["ARRMS_API_KEY_SECRET"] = "arrms-api-key"
    os.environ["ONSPRING_DEFAULT_APP_ID"] = "248"


def create_mock_lambda_context():
    """Create a mock Lambda context object."""

    class MockLambdaContext:
        function_name = "local-integration-test"
        function_version = "$LATEST"
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:local-test"
        memory_limit_in_mb = 512
        aws_request_id = "local-test-request-id"
        log_group_name = "/aws/lambda/local-test"
        log_stream_name = "local-test-stream"

        @staticmethod
        def get_remaining_time_in_millis():
            return 300000  # 5 minutes

    return MockLambdaContext()


def create_webhook_event(record_id: int, app_id: int = 248) -> Dict[str, Any]:
    """
    Create a mock API Gateway event for the webhook handler.

    Args:
        record_id: Onspring record ID
        app_id: Onspring app ID

    Returns:
        API Gateway event dict
    """
    body = json.dumps([{"RecordId": str(record_id), "AppId": str(app_id)}])

    return {
        "httpMethod": "POST",
        "path": "/webhook/onspring",
        "headers": {
            "Content-Type": "application/json",
            "x-api-key": "test-api-key",
        },
        "queryStringParameters": {"appId": str(app_id)},
        "body": body,
        "isBase64Encoded": False,
    }


def create_sync_event(app_id: int = 248, batch_size: int = 10) -> Dict[str, Any]:
    """
    Create a mock API Gateway event for the sync handler.

    Args:
        app_id: Onspring app ID to sync
        batch_size: Number of records per batch

    Returns:
        API Gateway event dict
    """
    body = json.dumps({"app_id": app_id, "batch_size": batch_size})

    return {
        "httpMethod": "POST",
        "path": "/sync/onspring-to-arrms",
        "headers": {
            "Content-Type": "application/json",
            "x-api-key": "test-api-key",
        },
        "body": body,
        "isBase64Encoded": False,
    }


def test_webhook_flow(record_id: int = 12345, app_id: int = 248):
    """
    Test the webhook handler flow.

    This simulates receiving a webhook from Onspring and processing it.
    """
    print("=" * 60)
    print("Testing Webhook Flow")
    print("=" * 60)
    print(f"Record ID: {record_id}")
    print(f"App ID: {app_id}")
    print()

    # Import handler (after environment is configured)
    from handlers.onspring_webhook import lambda_handler

    # Create event and context
    event = create_webhook_event(record_id, app_id)
    context = create_mock_lambda_context()

    print("Event:")
    print(json.dumps(event, indent=2))
    print()

    # Invoke handler
    print("Invoking webhook handler...")
    start_time = time.time()

    try:
        response = lambda_handler(event, context)
        elapsed = time.time() - start_time

        print()
        print("Response:")
        print(json.dumps(response, indent=2))
        print()
        print(f"Elapsed time: {elapsed:.2f}s")

        # Check response status
        status_code = response.get("statusCode", 500)
        if status_code == 200:
            print("SUCCESS: Webhook processed successfully")
        else:
            print(f"FAILED: Status code {status_code}")

        return response

    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        print(f"Elapsed time: {elapsed:.2f}s")
        import traceback

        traceback.print_exc()
        return None


def test_sync_flow(app_id: int = 248):
    """
    Test the sync handler flow.

    This simulates a batch sync from Onspring to ARRMS.
    """
    print("=" * 60)
    print("Testing Sync Flow")
    print("=" * 60)
    print(f"App ID: {app_id}")
    print()

    # Import handler (after environment is configured)
    from handlers.onspring_to_arrms import lambda_handler

    # Create event and context
    event = create_sync_event(app_id)
    context = create_mock_lambda_context()

    print("Event:")
    print(json.dumps(event, indent=2))
    print()

    # Invoke handler
    print("Invoking sync handler...")
    start_time = time.time()

    try:
        response = lambda_handler(event, context)
        elapsed = time.time() - start_time

        print()
        print("Response:")
        print(json.dumps(response, indent=2))
        print()
        print(f"Elapsed time: {elapsed:.2f}s")

        return response

    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        print(f"Elapsed time: {elapsed:.2f}s")
        import traceback

        traceback.print_exc()
        return None


def test_arrms_callback_flow(external_id: str = "12345"):
    """
    Test the ARRMS to Onspring callback flow.

    This simulates ARRMS sending statistics back to update Onspring.
    """
    print("=" * 60)
    print("Testing ARRMS Callback Flow")
    print("=" * 60)
    print(f"External ID: {external_id}")
    print()

    # Import handler (after environment is configured)
    from handlers.arrms_to_onspring import lambda_handler

    # Create event
    body = json.dumps({"external_id": external_id, "external_source": "onspring"})
    event = {
        "httpMethod": "POST",
        "path": "/callback/arrms",
        "headers": {"Content-Type": "application/json"},
        "body": body,
        "isBase64Encoded": False,
    }
    context = create_mock_lambda_context()

    print("Event:")
    print(json.dumps(event, indent=2))
    print()

    # Invoke handler
    print("Invoking ARRMS callback handler...")
    start_time = time.time()

    try:
        response = lambda_handler(event, context)
        elapsed = time.time() - start_time

        print()
        print("Response:")
        print(json.dumps(response, indent=2))
        print()
        print(f"Elapsed time: {elapsed:.2f}s")

        return response

    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        print(f"Elapsed time: {elapsed:.2f}s")
        import traceback

        traceback.print_exc()
        return None


def verify_onspring_updates(onspring_url: str = "http://localhost:5001"):
    """
    Verify what updates were made to the mock Onspring server.
    """
    import requests

    print("=" * 60)
    print("Verifying Onspring Updates")
    print("=" * 60)

    try:
        response = requests.get(f"{onspring_url}/admin/updates")
        updates = response.json().get("updates", [])

        if updates:
            print(f"Found {len(updates)} update(s):")
            for update in updates:
                print(json.dumps(update, indent=2))
        else:
            print("No updates recorded")

    except Exception as e:
        print(f"Error checking updates: {e}")


def main():
    parser = argparse.ArgumentParser(description="Local Integration Test Harness")
    parser.add_argument(
        "--onspring-url",
        default=os.environ.get("ONSPRING_API_URL", "http://localhost:5001"),
        help="Mock Onspring server URL",
    )
    parser.add_argument(
        "--arrms-url",
        default=os.environ.get("ARRMS_API_URL"),
        help="ARRMS API URL",
    )
    parser.add_argument(
        "--arrms-key",
        default=os.environ.get("ARRMS_API_KEY"),
        help="ARRMS API key",
    )
    parser.add_argument(
        "--record-id",
        type=int,
        default=12345,
        help="Record ID to test with",
    )
    parser.add_argument(
        "--app-id",
        type=int,
        default=248,
        help="App ID to test with",
    )
    parser.add_argument(
        "--test",
        choices=["webhook", "sync", "callback", "all"],
        default="webhook",
        help="Which test to run",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify Onspring updates after test",
    )

    args = parser.parse_args()

    # Validate ARRMS configuration
    if not args.arrms_url:
        print("WARNING: ARRMS_API_URL not set. Set it to test full integration.")
        print("         You can use: export ARRMS_API_URL=https://your-arrms-url")
        print()

    # Setup environment
    setup_environment(
        onspring_url=args.onspring_url,
        arrms_url=args.arrms_url,
        arrms_api_key=args.arrms_key,
    )

    print("Environment Configuration:")
    print(f"  ONSPRING_API_URL: {os.environ.get('ONSPRING_API_URL')}")
    print(f"  ARRMS_API_URL: {os.environ.get('ARRMS_API_URL', 'NOT SET')}")
    print(f"  LOCAL_DEV: {os.environ.get('LOCAL_DEV')}")
    print()

    # Run tests
    if args.test in ("webhook", "all"):
        test_webhook_flow(args.record_id, args.app_id)
        print()

    if args.test in ("sync", "all"):
        test_sync_flow(args.app_id)
        print()

    if args.test in ("callback", "all"):
        test_arrms_callback_flow(str(args.record_id))
        print()

    # Verify updates if requested
    if args.verify:
        verify_onspring_updates(args.onspring_url)


if __name__ == "__main__":
    main()
