# Lambda Integration Updates for ARRMS External System Support

**Branch**: `feature/arrms-external-system-integration`
**Related ARRMS Issue**: #178
**Status**: Ready for testing (pending ARRMS deployment)

## Summary

This branch updates the Onspring Lambda integration to align with ARRMS's new generic external system tracking fields. The changes replace placeholder implementations with actual API endpoints and field mappings.

## Changes Made

### 1. Authentication Update ✅

**File**: `src/adapters/arrms_client.py:99-105`

Changed from Bearer token to API Key authentication:

```python
# Before: "Authorization": f"Bearer {self.api_key}"
# After:  "X-API-Key": self.api_key
```

### 2. Questionnaire Endpoints ✅

**File**: `src/adapters/arrms_client.py:129-281`

Replaced placeholder `/records` endpoints with actual ARRMS questionnaire endpoints:

- `create_questionnaire()` - POST to `/api/v1/questionnaires`
- `update_questionnaire()` - PUT to `/api/v1/questionnaires/{id}`
- `get_questionnaire_by_external_id()` - GET with query params
- `upsert_questionnaire()` - Create or update based on external_id

### 3. Field Transformation ✅

**File**: `src/handlers/onspring_to_arrms.py:270-340`

Implemented actual field mapping from Onspring to ARRMS:

```python
{
    # ARRMS core fields
    "title": get_field_value("Title", "Untitled Questionnaire"),
    "client_name": get_field_value("Client"),
    "description": get_field_value("Description"),
    "due_date": get_field_value("DueDate"),

    # External system tracking
    "external_id": str(onspring_record.get("recordId")),
    "external_source": "onspring",
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

### 4. Document Upload ✅

**File**: `src/adapters/arrms_client.py:388-446`

Updated file upload to use questionnaire documents endpoint:

- Endpoint: `/api/v1/questionnaires/{id}/documents`
- Includes `external_id` (Onspring file ID)
- Includes `source_metadata` with Onspring file tracking

### 5. Handler Logic ✅

**File**: `src/handlers/onspring_to_arrms.py:191-268`

Updated sync logic to use new upsert methods:

```python
# Upsert questionnaire by Onspring record ID
onspring_record_id = str(record.get("recordId"))
result = arrms_client.upsert_questionnaire(
    external_id=onspring_record_id,
    data=transformed_record
)

# Upload documents with external metadata
arrms_client.upload_document(
    questionnaire_id=arrms_questionnaire_id,
    file_content=file_content,
    file_name=file_info["file_name"],
    content_type=file_info["content_type"],
    external_id=str(file_info["file_id"]),
    source_metadata={...}
)
```

### 6. Configuration ✅

**File**: `src/config/settings.py:54-57`

Added field mapping configuration:

```python
onspring_questionnaire_app_id: Optional[int] = Field(
    default=100, description="Onspring app ID for questionnaires"
)
```

### 7. Unit Tests ✅

**Files**:
- `tests/unit/test_arrms_client.py` (new)
- `tests/unit/test_transform.py` (new)

Added comprehensive unit tests for:
- Authentication with X-API-Key header
- Questionnaire creation with external_id
- Upsert logic (create vs update)
- Document upload with metadata
- Field transformation logic
- Edge cases (missing fields, empty data)

### 8. Documentation ✅

**File**: `README.md`

Updated documentation with:
- Field mapping table
- External system tracking explanation
- ARRMS API endpoints
- Authentication details
- Environment variables

## Testing Status

### Unit Tests
- ✅ ARRMS client authentication
- ✅ Questionnaire CRUD operations
- ✅ External ID query logic
- ✅ Upsert behavior (create vs update)
- ✅ Document upload with metadata
- ✅ Field transformation logic
- ✅ Edge cases and error handling

### Integration Tests
- ⏳ Pending ARRMS API availability
- ⏳ End-to-end sync flow
- ⏳ File upload integration
- ⏳ Error handling in production

## Deployment Checklist

### Prerequisites (waiting on ARRMS team)
- [ ] ARRMS issue #178 completed and deployed
- [ ] External system fields available in ARRMS
- [ ] API key authentication enabled in ARRMS
- [ ] Test ARRMS API endpoints available

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
   ```bash
   # Trigger webhook from Onspring sandbox
   # Verify questionnaire created in ARRMS
   # Check CloudWatch logs
   ```

6. **Deploy to Production**
   ```bash
   sam deploy --config-env prod
   ```

## Files Changed

```
modified:   src/adapters/arrms_client.py
modified:   src/config/settings.py
modified:   src/handlers/onspring_to_arrms.py
modified:   README.md
new file:   tests/unit/test_arrms_client.py
new file:   tests/unit/test_transform.py
new file:   INTEGRATION_UPDATES.md
```

## Breaking Changes

None - these changes are additive and align with ARRMS's new API contract.

## Rollback Plan

If issues occur after deployment:

1. Revert to previous Lambda version:
   ```bash
   sam deploy --config-env prod --parameter-overrides Version=previous
   ```

2. ARRMS can remain deployed (backward compatible)

3. No data loss (all changes are additive)

## Success Criteria

- [ ] Lambda authenticates with ARRMS using API key
- [ ] Lambda creates questionnaires with external_id
- [ ] Lambda queries questionnaires by external_id
- [ ] Lambda updates existing questionnaires (upsert)
- [ ] Lambda uploads files with Onspring metadata
- [ ] All unit tests pass
- [ ] End-to-end sync works in dev
- [ ] CloudWatch logs show successful syncs
- [ ] No errors in ARRMS API logs

## Next Steps

1. **Wait for ARRMS deployment** - ARRMS team to complete issue #178
2. **Coordinate testing** - Schedule integration testing session
3. **Merge to main** - After successful testing
4. **Deploy to production** - Coordinate with ARRMS production deployment

## Questions for ARRMS Team

1. ✅ API Key authentication header confirmed (`X-API-Key`)
2. ⏳ What format does ARRMS expect for `due_date`? (ISO 8601 assumed)
3. ⏳ Should `client_name` be validated against a clients table?
4. ⏳ Confirm document upload endpoint URL
5. ⏳ Should we track sync history in Lambda or rely on ARRMS's metadata?

## Notes

- All placeholder TODOs have been removed
- Code follows existing patterns in the codebase
- Logging statements added for debugging
- Error handling preserved and enhanced
- External metadata captures all Onspring context for future use
