"""
Unit tests for ARRMS Client
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from src.adapters.arrms_client import ARRMSClient
from src.utils.exceptions import ARRMSAPIError


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

    with patch("src.adapters.arrms_client.boto3.client") as mock_boto:
        # Mock Secrets Manager response
        mock_secrets = Mock()
        mock_secrets.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }
        mock_boto.return_value = mock_secrets

        client = ARRMSClient()
        client.session = mock_session

        return client


def test_create_session_uses_api_key_header(monkeypatch):
    """Test that session is created with X-API-Key header."""
    monkeypatch.setenv("ARRMS_API_URL", "https://arrms.example.com")
    monkeypatch.setenv("ARRMS_API_KEY_SECRET", "test-secret-name")

    with patch("src.adapters.arrms_client.boto3.client") as mock_boto:
        mock_secrets = Mock()
        mock_secrets.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }
        mock_boto.return_value = mock_secrets

        client = ARRMSClient()

        assert "X-API-Key" in client.session.headers
        assert client.session.headers["X-API-Key"] == "test-api-key-12345"
        assert "Authorization" not in client.session.headers


def test_create_questionnaire_with_external_id(arrms_client, mock_session):
    """Test questionnaire creation with Onspring tracking."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "uuid-123",
        "title": "SOC 2 Assessment",
        "external_id": "12345",
    }
    mock_session.post.return_value = mock_response

    data = {
        "title": "SOC 2 Assessment",
        "client_name": "Test Client",
        "external_id": "12345",
        "external_source": "onspring",
        "external_metadata": {"app_id": 100},
    }

    result = arrms_client.create_questionnaire(data)

    assert result["id"] == "uuid-123"
    mock_session.post.assert_called_once()
    call_args = mock_session.post.call_args

    # Verify URL
    assert call_args[0][0] == "https://arrms.example.com/api/v1/questionnaires"

    # Verify payload includes external tracking
    payload = call_args[1]["json"]
    assert payload["external_id"] == "12345"
    assert payload["external_source"] == "onspring"
    assert payload["title"] == "SOC 2 Assessment"


def test_update_questionnaire(arrms_client, mock_session):
    """Test updating existing questionnaire."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "uuid-existing",
        "title": "Updated Title",
    }
    mock_session.put.return_value = mock_response

    data = {"title": "Updated Title", "description": "Updated description"}

    result = arrms_client.update_questionnaire("uuid-existing", data)

    assert result["id"] == "uuid-existing"
    mock_session.put.assert_called_once()
    call_args = mock_session.put.call_args

    # Verify URL
    assert (
        call_args[0][0]
        == "https://arrms.example.com/api/v1/questionnaires/uuid-existing"
    )


def test_get_questionnaire_by_external_id_found(arrms_client, mock_session):
    """Test querying questionnaire by external ID when found."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "uuid-123", "external_id": "12345", "title": "Test"}
    ]
    mock_session.get.return_value = mock_response

    result = arrms_client.get_questionnaire_by_external_id("12345")

    assert result is not None
    assert result["id"] == "uuid-123"
    assert result["external_id"] == "12345"

    call_args = mock_session.get.call_args
    assert "params" in call_args[1]
    assert call_args[1]["params"]["external_id"] == "12345"
    assert call_args[1]["params"]["external_source"] == "onspring"


def test_get_questionnaire_by_external_id_not_found(arrms_client, mock_session):
    """Test querying questionnaire by external ID when not found."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_session.get.return_value = mock_response

    result = arrms_client.get_questionnaire_by_external_id("99999")

    assert result is None


def test_upsert_questionnaire_creates_new(arrms_client):
    """Test upsert creates new questionnaire when not found."""
    # Mock get_questionnaire_by_external_id to return None
    arrms_client.get_questionnaire_by_external_id = Mock(return_value=None)
    arrms_client.create_questionnaire = Mock(
        return_value={"id": "uuid-new", "title": "New Questionnaire"}
    )

    data = {"title": "New Questionnaire", "external_id": "12345"}

    result = arrms_client.upsert_questionnaire("12345", data)

    assert result["id"] == "uuid-new"
    arrms_client.create_questionnaire.assert_called_once_with(data)
    arrms_client.get_questionnaire_by_external_id.assert_called_once_with("12345")


def test_upsert_questionnaire_updates_existing(arrms_client):
    """Test upsert updates existing questionnaire."""
    # Mock get_questionnaire_by_external_id to return existing
    arrms_client.get_questionnaire_by_external_id = Mock(
        return_value={"id": "uuid-existing", "title": "Old Title"}
    )
    arrms_client.update_questionnaire = Mock(
        return_value={"id": "uuid-existing", "title": "Updated Title"}
    )

    data = {"title": "Updated Title"}

    result = arrms_client.upsert_questionnaire("12345", data)

    assert result["id"] == "uuid-existing"
    arrms_client.update_questionnaire.assert_called_once_with("uuid-existing", data)


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
    assert (
        call_args[0][0]
        == "https://arrms.example.com/api/v1/questionnaires/uuid-123/documents"
    )

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
