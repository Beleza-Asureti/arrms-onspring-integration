"""
Unit tests for Onspring to ARRMS transformation logic
"""

import pytest
from src.handlers.onspring_to_arrms import transform_record


def test_transform_record_with_all_fields():
    """Test transformation with all fields present."""
    onspring_record = {
        "recordId": 12345,
        "appId": 100,
        "fields": {
            "Title": {"value": "SOC 2 Assessment", "fieldId": 101},
            "Client": {"value": "Integrity Risk", "fieldId": 102},
            "DueDate": {"value": "2025-03-31", "fieldId": 103},
            "Status": {"value": "New", "fieldId": 104},
            "Description": {"value": "Annual compliance assessment", "fieldId": 105},
        },
    }

    result = transform_record(onspring_record)

    # Verify core ARRMS fields
    assert result["title"] == "SOC 2 Assessment"
    assert result["client_name"] == "Integrity Risk"
    assert result["due_date"] == "2025-03-31"
    assert result["description"] == "Annual compliance assessment"

    # Verify external system tracking
    assert result["external_id"] == "12345"
    assert result["external_source"] == "onspring"

    # Verify external metadata
    metadata = result["external_metadata"]
    assert metadata["app_id"] == 100
    assert metadata["onspring_status"] == "New"
    assert metadata["onspring_url"] == "https://app.onspring.com/record/12345"
    assert "synced_at" in metadata
    assert metadata["sync_type"] == "webhook"

    # Verify field IDs are captured
    field_ids = metadata["field_ids"]
    assert field_ids["title"] == 101
    assert field_ids["client"] == 102
    assert field_ids["due_date"] == 103
    assert field_ids["status"] == 104
    assert field_ids["description"] == 105


def test_transform_record_with_missing_optional_fields():
    """Test transformation when optional fields are missing."""
    onspring_record = {
        "recordId": 67890,
        "appId": 100,
        "fields": {
            "Title": {"value": "Minimal Record", "fieldId": 101},
            # No Client, DueDate, Status, or Description
        },
    }

    result = transform_record(onspring_record)

    # Verify required fields
    assert result["title"] == "Minimal Record"
    assert result["external_id"] == "67890"
    assert result["external_source"] == "onspring"

    # Verify optional fields are None or have defaults
    assert result["client_name"] is None
    assert result["due_date"] is None
    assert result["description"] is None

    # Verify external metadata
    metadata = result["external_metadata"]
    assert metadata["app_id"] == 100
    assert metadata["onspring_status"] is None


def test_transform_record_with_no_title():
    """Test transformation when title is missing (should use default)."""
    onspring_record = {
        "recordId": 11111,
        "appId": 100,
        "fields": {
            # No Title field
            "Client": {"value": "Test Client", "fieldId": 102},
        },
    }

    result = transform_record(onspring_record)

    # Should use default title
    assert result["title"] == "Untitled Questionnaire"
    assert result["client_name"] == "Test Client"


def test_transform_record_preserves_field_ids():
    """Test that field IDs are preserved for reverse mapping."""
    onspring_record = {
        "recordId": 99999,
        "appId": 200,
        "fields": {
            "Title": {"value": "Test", "fieldId": 501},
            "Client": {"value": "ABC Corp", "fieldId": 502},
        },
    }

    result = transform_record(onspring_record)

    field_ids = result["external_metadata"]["field_ids"]

    # Verify all field IDs are captured
    assert field_ids["title"] == 501
    assert field_ids["client"] == 502

    # Missing fields should have None
    assert field_ids["due_date"] is None
    assert field_ids["status"] is None
    assert field_ids["description"] is None


def test_transform_record_creates_onspring_url():
    """Test that Onspring URL is correctly generated."""
    onspring_record = {
        "recordId": 54321,
        "appId": 100,
        "fields": {"Title": {"value": "Test", "fieldId": 101}},
    }

    result = transform_record(onspring_record)

    assert (
        result["external_metadata"]["onspring_url"]
        == "https://app.onspring.com/record/54321"
    )


def test_transform_record_with_empty_fields():
    """Test transformation when fields dictionary is empty."""
    onspring_record = {"recordId": 11111, "appId": 100, "fields": {}}

    result = transform_record(onspring_record)

    # Should use defaults
    assert result["title"] == "Untitled Questionnaire"
    assert result["client_name"] is None
    assert result["due_date"] is None
    assert result["description"] is None
    assert result["external_id"] == "11111"
