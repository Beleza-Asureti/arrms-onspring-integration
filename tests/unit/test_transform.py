"""
Unit tests for Onspring to ARRMS transformation logic
"""

from unittest.mock import Mock

from handlers.onspring_to_arrms import transform_record


def test_transform_record_with_all_fields():
    """Test transformation with all fields present."""
    onspring_record = {
        "recordId": 12345,
        "appId": 100,
        "fieldData": [
            {"fieldId": 14872, "type": "Date", "value": "2025-03-31T00:00:00Z"},
            {"fieldId": 14888, "type": "Text", "value": "Annual compliance assessment"},
            {"fieldId": 14947, "type": "Integer", "value": 1},
        ],
    }

    # Mock OnspringClient
    mock_client = Mock()
    mock_client.resolve_reference_field.return_value = "Test Company"

    result = transform_record(onspring_record, mock_client)

    # Verify core ARRMS fields
    assert result["due_date"] == "2025-03-31T00:00:00Z"
    assert result["notes"] == "Annual compliance assessment"
    assert result["requester_name"] == "Test Company"

    # Verify external system tracking
    assert result["external_id"] == "12345"
    assert result["external_source"] == "onspring"

    # Verify external metadata
    metadata = result["external_metadata"]
    assert metadata["app_id"] == 100
    assert metadata["onspring_url"] == "https://app.onspring.com/record/12345"
    assert "synced_at" in metadata
    assert metadata["sync_type"] == "webhook"

    # Verify field IDs are captured
    field_ids = metadata["field_ids"]
    assert field_ids["due_date"] == 14872
    assert field_ids["notes"] == 14888
    assert field_ids["requester_name"] == 14947


def test_transform_record_with_missing_optional_fields():
    """Test transformation when optional fields are missing."""
    onspring_record = {
        "recordId": 67890,
        "appId": 100,
        "fieldData": [],  # No fields
    }

    # Mock OnspringClient
    mock_client = Mock()

    result = transform_record(onspring_record, mock_client)

    # Verify required fields with defaults
    assert result["title"] == "Untitled Questionnaire"
    assert result["external_id"] == "67890"
    assert result["external_source"] == "onspring"

    # Verify optional fields are None
    assert result["due_date"] is None
    assert result["notes"] is None
    assert result["requester_name"] is None

    # Verify external metadata
    metadata = result["external_metadata"]
    assert metadata["app_id"] == 100


def test_transform_record_with_no_title():
    """Test transformation when title is missing (should use default)."""
    onspring_record = {
        "recordId": 11111,
        "appId": 100,
        "fieldData": [],  # No fields, so no title
    }

    # Mock OnspringClient
    mock_client = Mock()

    result = transform_record(onspring_record, mock_client)

    # Should use default title
    assert result["title"] == "Untitled Questionnaire"


def test_transform_record_preserves_field_ids():
    """Test that field IDs are preserved for reverse mapping."""
    onspring_record = {
        "recordId": 99999,
        "appId": 200,
        "fieldData": [
            {"fieldId": 14872, "type": "Date", "value": "2025-12-31T00:00:00Z"},
            {"fieldId": 14888, "type": "Text", "value": "Test notes"},
        ],
    }

    # Mock OnspringClient
    mock_client = Mock()

    result = transform_record(onspring_record, mock_client)

    field_ids = result["external_metadata"]["field_ids"]

    # Verify hardcoded field IDs are in metadata
    assert field_ids["due_date"] == 14872
    assert field_ids["notes"] == 14888
    assert field_ids["requester_name"] == 14947


def test_transform_record_creates_onspring_url():
    """Test that Onspring URL is correctly generated."""
    onspring_record = {
        "recordId": 54321,
        "appId": 100,
        "fieldData": [],
    }

    # Mock OnspringClient
    mock_client = Mock()

    result = transform_record(onspring_record, mock_client)

    assert result["external_metadata"]["onspring_url"] == "https://app.onspring.com/record/54321"


def test_transform_record_with_empty_fields():
    """Test transformation when fieldData array is empty."""
    onspring_record = {"recordId": 11111, "appId": 100, "fieldData": []}

    # Mock OnspringClient
    mock_client = Mock()

    result = transform_record(onspring_record, mock_client)

    # Should use defaults
    assert result["title"] == "Untitled Questionnaire"
    assert result["due_date"] is None
    assert result["notes"] is None
    assert result["requester_name"] is None
    assert result["external_id"] == "11111"


def test_transform_record_resolves_company_reference():
    """Test that company reference field is resolved correctly."""
    onspring_record = {
        "recordId": 123,
        "appId": 248,
        "fieldData": [
            {"fieldId": 14947, "type": "Integer", "value": 5},  # Company reference
        ],
    }

    # Mock OnspringClient
    mock_client = Mock()
    mock_client.resolve_reference_field.return_value = "Acme Corporation"

    result = transform_record(onspring_record, mock_client)

    # Verify reference was resolved
    assert result["requester_name"] == "Acme Corporation"

    # Verify the resolver was called with correct parameters
    mock_client.resolve_reference_field.assert_called_once_with(
        referenced_app_id=249,
        referenced_record_id=5,
        field_id=14949,
    )


def test_transform_record_handles_failed_company_resolution():
    """Test that failed company resolution doesn't break the transform."""
    onspring_record = {
        "recordId": 123,
        "appId": 248,
        "fieldData": [
            {"fieldId": 14947, "type": "Integer", "value": 999},  # Invalid company reference
        ],
    }

    # Mock OnspringClient to raise an exception
    mock_client = Mock()
    mock_client.resolve_reference_field.side_effect = Exception("Record not found")

    result = transform_record(onspring_record, mock_client)

    # Should return None for requester_name when resolution fails
    assert result["requester_name"] is None
