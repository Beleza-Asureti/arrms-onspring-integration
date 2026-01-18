# Lambda Integration Updates for ARRMS External System Support

**Branch**: `feature/arrms-external-system-integration`
**Related ARRMS PR**: #179 (merged)
**Status**: Ready for testing (pending ARRMS deployment)

## Summary

This branch updates the Onspring Lambda integration to align with ARRMS's new external system tracking using a separate `external_references` table with array-based relationships. The changes replace placeholder implementations with actual file upload workflow and external reference parsing.

## IMPORTANT: API Response Format Change

ARRMS implemented external system tracking differently than originally planned. Instead of inline fields on questionnaires, they use a separate `external_references` table:

**Response Structure:**

```json
{
  "id": "uuid",
  "name": "Questionnaire Name",
  "external_references": [
    {
      "id": "ref-uuid",
      "external_id": "12345",
      "external_source": "onspring",
      "external_metadata": {"app_id": 100, ...},
      "sync_status": null,
      "last_synced_at": null
    }
  ]
}
```

**Key Implications:**
- Response parsing must access `external_references[0]["external_id"]` instead of `external_id`
- Supports multiple external systems per questionnaire (future-proofing)
- Request format unchanged - still send `external_id`, `external_source`, `external_metadata` as form fields
- **No query-by-external_id support yet** - can't do upsert pattern, must rely on Onspring to not send duplicates

## Changes Made

### 1. Authentication Update ✅

**File**: [src/adapters/arrms_client.py:99-105](src/adapters/arrms_client.py#L99-L105)

Changed from Bearer token to API Key authentication:

```python
# Before: "Authorization": f"Bearer {self.api_key}"
# After:  "X-API-Key": self.api_key
```

### 2. Upload Endpoint ✅

**File**: [src/adapters/arrms_client.py:129-211](src/adapters/arrms_client.py#L129-L211)

Replaced create/update/upsert methods with `upload_questionnaire()`:

- Endpoint: `POST /api/v1/questionnaires/upload`
- Accepts multipart form data with Excel file
- Includes `external_id`, `external_source`, `external_metadata` as form fields
- Supports additional fields: `requester_name`, `urgency`, `assessment_type`, `due_date`, `notes`
- Returns response with `external_references` array

### 3. External Reference Parsing ✅

**File**: [src/adapters/arrms_client.py:213-248](src/adapters/arrms_client.py#L213-L248)

Added `parse_external_reference()` helper method:

```python
def parse_external_reference(
    self, response_data: Dict[str, Any], external_source: str = "onspring"
) -> Optional[Dict[str, Any]]:
    """Extract external reference from ARRMS response."""
    refs = response_data.get("external_references", [])
    for ref in refs:
        if ref.get("external_source") == external_source:
            return ref
    return None
```

### 4. Sync Handler Workflow ✅

**File**: [src/handlers/onspring_to_arrms.py:192-333](src/handlers/onspring_to_arrms.py#L192-L333)

Updated sync logic for file-based upload workflow:

1. Transform Onspring record to extract metadata
2. Find questionnaire file (Excel format) from Onspring attachments
3. Download questionnaire file to temporary location
4. Upload file to ARRMS with external tracking fields
5. Parse `external_references` from response to verify creation
6. Upload additional supporting documents separately

**Key Changes:**
- Downloads Excel file from Onspring first
- Uses `tempfile` for temporary file storage
- Uploads file with form data instead of JSON
- Verifies external reference creation
- Handles missing questionnaire files gracefully

### 5. Field Transformation ✅

**File**: [src/handlers/onspring_to_arrms.py:343-415](src/handlers/onspring_to_arrms.py#L343-L415)

Transformation still extracts metadata from Onspring fields:

```python
{
    # Metadata for form fields
    "requester_name": get_field_value("Requester"),
    "urgency": get_field_value("Urgency"),
    "assessment_type": get_field_value("AssessmentType"),
    "due_date": get_field_value("DueDate"),
    "notes": get_field_value("Description"),

    # External system tracking metadata
    "external_metadata": {
        "app_id": onspring_record.get("appId"),
        "onspring_status": get_field_value("Status"),
        "onspring_url": f"https://app.onspring.com/record/{recordId}",
        "field_ids": {...},
        "synced_at": datetime.utcnow().isoformat(),
        "sync_type": "webhook"
    }
}
```

### 6. Unit Tests ✅

**File**: [tests/unit/test_arrms_client.py](tests/unit/test_arrms_client.py)

Updated tests for new response structure:

- `test_upload_questionnaire_with_external_id()` - Tests file upload with external_references
- `test_parse_external_reference_found()` - Tests parsing helper
- `test_parse_external_reference_not_found()` - Tests missing reference
- `test_parse_external_reference_empty_array()` - Tests empty array
- `test_parse_external_reference_multiple_sources()` - Tests multi-source filtering
- `test_upload_document_with_metadata()` - Tests supporting document upload

### 7. Documentation ✅

Updated README and integration docs to reflect:
- File upload workflow
- External references array structure
- No upsert support (yet)
- Temporary file handling

## Removed Features

The following methods were **removed** because they're not supported in the current ARRMS implementation:

- ❌ `create_questionnaire()` - Replaced with `upload_questionnaire()`
- ❌ `update_questionnaire()` - No update endpoint available
- ❌ `get_questionnaire_by_external_id()` - Query by external_id not implemented in ARRMS yet
- ❌ `upsert_questionnaire()` - Can't upsert without query support

**Workaround**: Onspring webhooks should only send create events, not updates. The lambda will create a new questionnaire each time (no deduplication).

## Files Changed

```
modified:   src/adapters/arrms_client.py
modified:   src/handlers/onspring_to_arrms.py
modified:   tests/unit/test_arrms_client.py
modified:   tests/unit/test_transform.py
modified:   INTEGRATION_UPDATES.md
modified:   README.md
```

## Deployment Checklist

### Prerequisites
- ✅ ARRMS PR #179 merged with external_references table
- ⏳ ARRMS deployed with migration applied
- ⏳ ARRMS API upload endpoint available
- ⏳ API key authentication enabled in ARRMS

### Lambda Deployment Steps

1. **Generate ARRMS API Key**
   ```bash
   # In ARRMS application
   # Create new API key for Lambda integration
   ```

2. **Update Secrets Manager**
   ```bash
   aws secretsmanager update-secret \
       --secret-id /arrms-integration/arrms/api-key \
       --secret-string "new-arrms-api-key"
   ```

3. **Run Unit Tests**
   ```bash
   pytest tests/unit/
   ```

4. **Build and Deploy to Dev**
   ```bash
   sam build
   sam deploy --config-env dev
   ```

5. **Test Integration**
   - Trigger webhook from Onspring with Excel attachment
   - Verify questionnaire uploaded to ARRMS
   - Check external_references array in response
   - Verify CloudWatch logs

6. **Deploy to Production**
   ```bash
   sam deploy --config-env prod
   ```

## Testing Status

### Unit Tests ✅
- ARRMS client authentication with X-API-Key
- Questionnaire file upload with external tracking
- External reference parsing from array responses
- Multiple external sources filtering
- Document upload with metadata
- Error handling

### Integration Tests ⏳
- Pending ARRMS API availability
- End-to-end file upload flow
- External reference verification
- Supporting document uploads

## Limitations & Known Issues

1. **No Upsert Support**: ARRMS doesn't support querying by external_id yet, so we can't check for duplicates. The lambda will create a new questionnaire every time the webhook fires.

2. **Questionnaire File Required**: The lambda expects an Excel file attachment in the Onspring record. If no Excel file is found, the sync fails.

3. **First Excel File Used**: If multiple Excel files are attached, only the first one is used as the questionnaire. Others become supporting documents.

4. **No Update Capability**: Once a questionnaire is created in ARRMS, the lambda can't update it. Changes in Onspring require manual updates in ARRMS.

## Future Enhancements

1. **Query by External ID**: Once ARRMS adds support, implement upsert logic to prevent duplicates
2. **Local Mapping Cache**: Store Onspring ID → ARRMS ID mapping in DynamoDB for deduplication
3. **Configurable File Field**: Allow configuration of which Onspring field contains the questionnaire
4. **Bulk Upload Support**: Batch process multiple questionnaires efficiently
5. **Update Support**: Add update capability once ARRMS provides endpoint

## Success Criteria

- ✅ Lambda authenticates with ARRMS using API key
- ✅ Lambda uploads questionnaire files with external tracking
- ✅ External references array parsed correctly
- ✅ Supporting documents uploaded separately
- ⏳ All unit tests pass
- ⏳ End-to-end sync works in dev
- ⏳ CloudWatch logs show successful syncs
- ⏳ No errors in ARRMS API logs

## Notes

- External tracking metadata captures all Onspring context
- Temporary files cleaned up after upload
- Error handling preserved and enhanced
- Logging improved for debugging
- Code follows existing patterns in codebase
