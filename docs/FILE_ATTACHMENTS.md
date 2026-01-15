# File Attachment Handling

This document describes how the ARRMS-Onspring Integration Service handles file attachments during record synchronization.

## Overview

When records are synchronized from Onspring to ARRMS, any file attachments (documents, images, PDFs, etc.) are automatically downloaded from Onspring and uploaded to the corresponding ARRMS record.

## Supported Field Types

The integration automatically processes these Onspring field types:
- **FileList**: Multiple file attachments
- **AttachmentList**: Multiple attachment files

## How It Works

### 1. Webhook Flow

When Onspring triggers a webhook for a record change:

1. **Fetch Record**: Retrieve the full record data from Onspring
2. **Sync Record**: Transform and upsert the record to ARRMS
3. **Extract Files**: Parse the record to identify file attachments
4. **Download Files**: Download each file from Onspring API
5. **Upload Files**: Upload each file to the ARRMS record
6. **Track Metrics**: Report success/failure counts for files

### 2. Batch Sync Flow

When batch synchronization runs:

1. **Retrieve Records**: Get all records from Onspring app
2. **For Each Record**:
   - Sync record data to ARRMS
   - Extract and process file attachments
   - Download from Onspring, upload to ARRMS
3. **Report Summary**: Include file sync counts in results

## File Metadata

Each file includes the following metadata when uploaded to ARRMS:

```json
{
  "file_name": "document.pdf",
  "content_type": "application/pdf",
  "source": "onspring",
  "onspring_record_id": 16,
  "onspring_field_id": 123,
  "onspring_file_id": 456,
  "notes": "Optional notes from Onspring"
}
```

## API Endpoints

### Onspring File Operations

#### Get File Information
```
GET /Files/recordId/{recordId}/fieldId/{fieldId}/fileId/{fileId}
```
Returns file metadata without downloading content.

#### Download File Content
```
GET /Files/recordId/{recordId}/fieldId/{fieldId}/fileId/{fileId}/file
```
Downloads the actual file content as bytes.

### ARRMS File Upload (Placeholder)

```
POST /records/{recordId}/files
Content-Type: multipart/form-data
```

**Note**: The ARRMS file upload endpoint is a placeholder. The actual endpoint URL and payload format need to be confirmed when the ARRMS API is available.

## Error Handling

File attachment processing is **non-blocking**:

- If a file fails to download or upload, it's logged as an error
- The record sync continues successfully
- Other files in the record are still processed
- File failure counts are tracked in metrics and responses

This ensures that file attachment issues don't prevent critical record data from syncing.

## Webhook Response

Webhook responses include file sync information:

```json
{
  "message": "Webhook processed successfully",
  "recordId": 16,
  "appId": 248,
  "arrmsSynced": true,
  "filesSynced": 3,
  "filesFailed": 0
}
```

## Batch Sync Response

Batch sync responses include file counts in the summary:

```json
{
  "message": "Sync completed",
  "summary": {
    "total_records": 100,
    "successful": 98,
    "failed": 2,
    "files_synced": 245,
    "files_failed": 5
  },
  "errors": []
}
```

## CloudWatch Metrics

### File Sync Metrics

| Metric Name | Unit | Description |
|-------------|------|-------------|
| `FilesSynced` | Count | Number of files successfully synced |
| `FilesSyncFailed` | Count | Number of files that failed to sync |

### Example Query

```
SELECT SUM(FilesSynced) FROM ARRMSIntegration
WHERE FunctionName = 'arrms-onspring-integration-dev-onspring-webhook'
```

## Logging

File operations are logged with contextual information:

**Info Level**:
```
Processing 3 file attachments
Downloaded file 456, size: 1048576 bytes
Synced file: document.pdf
```

**Error Level**:
```
Failed to sync file report.xlsx
  error: Connection timeout
  file_info: {record_id: 16, field_id: 123, file_id: 789}
```

## Configuration

No additional configuration is required. File processing is automatic when:
1. Records contain FileList or AttachmentList fields
2. Those fields have file attachments

## Performance Considerations

### File Size Limits

- **Lambda Timeout**: Default 30-60 seconds
- **Large Files**: Files >10MB may require longer timeouts
- **Lambda Memory**: Default 512MB may need adjustment for large files

### Recommendation for Large Files

If your Onspring records contain large files (>10MB):

1. Increase Lambda timeout in `template.yaml`:
```yaml
Globals:
  Function:
    Timeout: 120  # 2 minutes
```

2. Increase Lambda memory:
```yaml
Globals:
  Function:
    MemorySize: 1024  # 1GB
```

### Concurrent Processing

Files are processed sequentially within each record to:
- Maintain order
- Avoid API rate limits
- Prevent memory issues

For high-volume scenarios, consider:
- Processing files asynchronously via SQS
- Using S3 as intermediate storage
- Implementing batch file upload to ARRMS

## TODO: ARRMS API Integration

The ARRMS file upload implementation is currently a **placeholder**. When the ARRMS API is available:

### Update Required in `arrms_client.py`

```python
def upload_file(self, record_id, file_content, file_name, content_type, metadata):
    # TODO: Update this URL when ARRMS file upload API is available
    url = f"{self.base_url}/records/{record_id}/files"

    # TODO: Confirm if ARRMS expects multipart/form-data or JSON with base64
    # Current implementation uses multipart/form-data
```

### Questions to Answer:

1. **Endpoint URL**: What is the correct ARRMS file upload endpoint?
2. **Payload Format**: Does ARRMS expect:
   - Multipart/form-data (current implementation)
   - JSON with base64-encoded file content
   - Different format?
3. **Authentication**: Same API key or different credentials?
4. **Response Format**: What does ARRMS return on successful upload?
5. **Error Codes**: What errors can ARRMS return?

## Testing File Attachments

### Test with Onspring Webhook

```bash
# Create a test event with file attachments
curl -X POST \
  -H "x-api-key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '[{"RecordId": "16"}]' \
  "https://YOUR_API_URL/webhook/onspring?appId=248"
```

### Check CloudWatch Logs

```bash
aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-webhook \
  --follow \
  --filter-pattern "file" \
  --region us-east-1
```

### Monitor Metrics

Check CloudWatch Metrics dashboard:
- Namespace: `ARRMSIntegration`
- Metrics: `FilesSynced`, `FilesSyncFailed`

## Troubleshooting

### Files Not Syncing

**Check Logs**:
```bash
aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-webhook \
  --since 10m --region us-east-1
```

**Common Issues**:
1. **Onspring API Key**: Verify key has file download permissions
2. **Field Type**: Confirm fields are FileList or AttachmentList
3. **Lambda Timeout**: Check if timeout is sufficient for file size
4. **ARRMS Endpoint**: Placeholder endpoint will fail (expected until ARRMS API ready)

### High File Failure Rate

If `FilesSyncFailed` is consistently high:

1. **Check ARRMS API Status**: Is the ARRMS endpoint available?
2. **Review Error Logs**: What specific errors are occurring?
3. **File Size**: Are files too large for Lambda/ARRMS limits?
4. **Network Issues**: Temporary connectivity problems?

## Example: Processing Record with Files

```python
# Extract files from Onspring record
files = onspring_client.get_record_files(record_data)
# Returns:
# [
#   {
#     "record_id": 16,
#     "field_id": 123,
#     "file_id": 456,
#     "file_name": "document.pdf",
#     "file_size": 1048576,
#     "content_type": "application/pdf",
#     "notes": "Q4 Financial Report"
#   },
#   {
#     "record_id": 16,
#     "field_id": 123,
#     "file_id": 457,
#     "file_name": "chart.png",
#     "file_size": 524288,
#     "content_type": "image/png",
#     "notes": null
#   }
# ]

# Download and upload each file
for file_info in files:
    # Download from Onspring
    file_content = onspring_client.download_file(
        record_id=file_info["record_id"],
        field_id=file_info["field_id"],
        file_id=file_info["file_id"]
    )

    # Upload to ARRMS
    arrms_client.upload_file(
        record_id=arrms_record_id,
        file_content=file_content,
        file_name=file_info["file_name"],
        content_type=file_info["content_type"],
        metadata={
            "source": "onspring",
            "onspring_record_id": record_id,
            "onspring_field_id": file_info["field_id"],
            "onspring_file_id": file_info["file_id"],
            "notes": file_info.get("notes")
        }
    )
```

## Security Considerations

### File Content Validation

Consider adding validation for:
- File size limits
- Allowed content types
- Virus scanning
- Content inspection

### Data Privacy

File attachments may contain sensitive information:
- Ensure Lambda has appropriate IAM permissions
- Consider encryption in transit and at rest
- Implement access controls in ARRMS
- Audit file access logs

## Future Enhancements

Potential improvements:
1. **Parallel Processing**: Download/upload files concurrently
2. **S3 Staging**: Use S3 as intermediate storage for large files
3. **Retry Logic**: Automatic retry for failed file operations
4. **Compression**: Compress files before upload to reduce bandwidth
5. **Delta Sync**: Only sync files that changed
6. **File Versioning**: Track file version history
7. **Async Processing**: Use SQS for asynchronous file processing

## References

- [Onspring Files API Documentation](https://software.onspring.com/hubfs/Onspring%20API%20v2/index.html#/Files)
- [AWS Lambda File Processing Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Multipart Form Data RFC](https://www.w3.org/TR/html401/interact/forms.html#h-17.13.4)
