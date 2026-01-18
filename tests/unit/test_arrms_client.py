"""
Unit tests for ARRMS Client
"""

import json
from unittest.mock import Mock, mock_open, patch

import pytest

from adapters.arrms_client import ARRMSClient


@pytest.fixture
def mock_session():
    """Create a mock requests session."""
    session = Mock()
    session.headers = {}
    return session


@pytest.fixture
def arrms_client(monkeypatch, mock_session):
    """Create ARRMS client with mocked dependencies."""
    monkeypatch.setenv("ARRMS_API_URL", "https://arrms.example.com")
    monkeypatch.setenv("ARRMS_API_KEY_SECRET", "test-secret-name")

    with patch("adapters.arrms_client.boto3.client") as mock_boto:
        # Mock Secrets Manager response
        mock_secrets = Mock()
        mock_secrets.get_secret_value.return_value = {"SecretString": "test-api-key-12345"}
        mock_boto.return_value = mock_secrets

        client = ARRMSClient()
        client.session = mock_session

        return client


def test_create_session_uses_api_key_header(monkeypatch):
    """Test that session is created with X-API-Key header."""
    monkeypatch.setenv("ARRMS_API_URL", "https://arrms.example.com")
    monkeypatch.setenv("ARRMS_API_KEY_SECRET", "test-secret-name")

    with patch("adapters.arrms_client.boto3.client") as mock_boto:
        mock_secrets = Mock()
        mock_secrets.get_secret_value.return_value = {"SecretString": "test-api-key-12345"}
        mock_boto.return_value = mock_secrets

        client = ARRMSClient()

        assert "X-API-Key" in client.session.headers
        assert client.session.headers["X-API-Key"] == "test-api-key-12345"
        assert "Authorization" not in client.session.headers


def test_upload_questionnaire_with_external_id(arrms_client, mock_session):
    """Test questionnaire upload with Onspring tracking and external_references array."""
    mock_response = Mock()

    # Mock response with external_references array
    mock_response.json.return_value = {
        "id": "uuid-123",
        "name": "Test Questionnaire",
        "external_references": [
            {
                "id": "ref-uuid-456",
                "external_id": "12345",
                "external_source": "onspring",
                "external_metadata": {"app_id": 100},
                "sync_status": None,
                "last_synced_at": None,
            }
        ],
    }
    mock_session.post.return_value = mock_response

    # Mock file open
    test_file_content = b"test file content"
    with patch("builtins.open", mock_open(read_data=test_file_content)):
        result = arrms_client.upload_questionnaire(
            file_path="/tmp/test.xlsx",
            external_id="12345",
            external_source="onspring",
            external_metadata={"app_id": 100},
            requester_name="John Doe",
            urgency="High",
        )

    assert result["id"] == "uuid-123"
    assert len(result["external_references"]) == 1
    assert result["external_references"][0]["external_id"] == "12345"

    mock_session.post.assert_called_once()
    call_args = mock_session.post.call_args

    # Verify URL (integrations endpoint for API key auth)
    assert call_args[0][0] == "https://arrms.example.com/api/v1/integrations/questionnaires/upload"

    # Verify form data includes external tracking and additional fields
    data = call_args[1]["data"]
    assert data["external_id"] == "12345"
    assert data["external_source"] == "onspring"
    assert data["requester_name"] == "John Doe"
    assert data["urgency"] == "High"

    # Verify external_metadata is JSON string
    metadata = json.loads(data["external_metadata"])
    assert metadata["app_id"] == 100


def test_parse_external_reference_found(arrms_client):
    """Test parsing external reference from response."""
    response_data = {
        "id": "uuid-123",
        "name": "Test",
        "external_references": [
            {
                "id": "ref-uuid-456",
                "external_id": "12345",
                "external_source": "onspring",
                "external_metadata": {"app_id": 100},
            }
        ],
    }

    external_ref = arrms_client.parse_external_reference(response_data, "onspring")

    assert external_ref is not None
    assert external_ref["external_id"] == "12345"
    assert external_ref["external_source"] == "onspring"
    assert external_ref["external_metadata"]["app_id"] == 100


def test_parse_external_reference_not_found(arrms_client):
    """Test parsing external reference when source not found."""
    response_data = {
        "id": "uuid-123",
        "name": "Test",
        "external_references": [
            {
                "id": "ref-uuid-456",
                "external_id": "99999",
                "external_source": "different_source",
                "external_metadata": {},
            }
        ],
    }

    external_ref = arrms_client.parse_external_reference(response_data, "onspring")

    assert external_ref is None


def test_parse_external_reference_empty_array(arrms_client):
    """Test parsing external reference when array is empty."""
    response_data = {"id": "uuid-123", "name": "Test", "external_references": []}

    external_ref = arrms_client.parse_external_reference(response_data, "onspring")

    assert external_ref is None


def test_parse_external_reference_multiple_sources(arrms_client):
    """Test parsing external reference with multiple sources."""
    response_data = {
        "id": "uuid-123",
        "name": "Test",
        "external_references": [
            {
                "id": "ref-uuid-1",
                "external_id": "99999",
                "external_source": "servicenow",
                "external_metadata": {},
            },
            {
                "id": "ref-uuid-2",
                "external_id": "12345",
                "external_source": "onspring",
                "external_metadata": {"app_id": 100},
            },
        ],
    }

    external_ref = arrms_client.parse_external_reference(response_data, "onspring")

    assert external_ref is not None
    assert external_ref["external_id"] == "12345"
    assert external_ref["external_source"] == "onspring"


def test_upload_document_with_metadata(arrms_client, mock_session):
    """Test document upload with Onspring metadata."""
    mock_response = Mock()
    mock_response.json.return_value = {"file_id": "file-123", "status": "uploaded"}
    mock_session.post.return_value = mock_response

    result = arrms_client.upload_document(
        questionnaire_id="uuid-123",
        file_content=b"test file content",
        file_name="evidence.pdf",
        content_type="application/pdf",
        external_id="999",
        source_metadata={"onspring_record_id": 12345, "notes": "Test file"},
    )

    assert result["file_id"] == "file-123"
    mock_session.post.assert_called_once()

    call_args = mock_session.post.call_args

    # Verify URL
    assert call_args[0][0] == "https://arrms.example.com/api/v1/questionnaires/uuid-123/documents"

    # Verify files and data
    assert "files" in call_args[1]
    assert "data" in call_args[1]

    data = call_args[1]["data"]
    assert data["external_id"] == "999"
    assert data["external_source"] == "onspring"

    # Verify source_metadata is JSON
    source_metadata = json.loads(data["source_metadata"])
    assert source_metadata["onspring_record_id"] == 12345
    assert source_metadata["notes"] == "Test file"
