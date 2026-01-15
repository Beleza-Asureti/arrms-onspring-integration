# Onspring REST API Outcome Setup Guide

This guide explains how to configure Onspring's REST API Outcome trigger to send record updates to the ARRMS integration service.

## Understanding Onspring REST API Outcomes

Onspring uses **REST API Outcomes** in workflows rather than traditional webhooks. When workflow conditions are met, Onspring makes an HTTP POST request to your configured endpoint.

### Advantages of This Approach

- **Lightweight**: Onspring sends just the RecordId - `[{"RecordId": "16"}]`
- **Flexible**: Lambda fetches full record details as needed from Onspring API
- **Decoupled**: No dependency on Onspring to send complex payloads
- **Maintainable**: Lambda controls what data is retrieved and how it's transformed

## Integration Endpoint

**Webhook URL**: `https://tfyp2toag2.execute-api.us-east-1.amazonaws.com/dev/webhook/onspring?appId=YOUR_APP_ID`

**Important**: Replace `YOUR_APP_ID` with your actual Onspring Application ID

## Configuration Steps

### 1. Get Your Onspring Application ID

1. Log into Onspring
2. Navigate to your application (e.g., Risks, Controls, etc.)
3. Look in the URL or application settings to find the App ID
4. Example: If URL is `.../app/100/...`, your App ID is `100`

### 2. Configure REST API Outcome in Onspring Workflow

1. **Navigate to Workflow**
   - Go to Administration > Apps > [Your Application]
   - Select "Workflows" tab
   - Create new workflow or edit existing

2. **Add REST API Outcome**
   - In workflow editor, add a new "Outcome"
   - Select "REST API" as the outcome type

3. **Configure the Outcome**

   **URL**:
   ```
   https://tfyp2toag2.execute-api.us-east-1.amazonaws.com/dev/webhook/onspring?appId=YOUR_APP_ID
   ```
   Replace `YOUR_APP_ID` with your actual application ID.

   **Method**: `POST`

   **Headers**:
   - Name: `x-api-key`
   - Value: `qx5Y2ookMbSJfERExOF427sfl2OKnTT74eRlBjc0`

   **Body**:
   ```json
   [{"RecordId": "[RecordId]"}]
   ```

   Note: Use Onspring's token syntax `[RecordId]` which will be replaced with the actual record ID when triggered.

   **Content-Type**: `application/json`

4. **Set Trigger Conditions**
   - Define when this REST API Outcome should fire
   - Examples:
     - When a record is created
     - When Status changes to "Active"
     - When specific fields are updated
     - When a record is moved to a certain phase

5. **Test the Integration**
   - Use the "Test Request" button in Onspring
   - Select a test record
   - Verify the request succeeds

### 3. Verify in AWS

After triggering the workflow in Onspring:

1. **Check CloudWatch Logs**:
   ```bash
   aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-webhook --follow
   ```

2. **Expected Log Output**:
   ```
   Received Onspring webhook event
   Webhook payload: [{"RecordId": "16"}]
   Processing webhook: record_id=16, app_id=100
   Fetching record 16 from Onspring app 100
   Successfully processed webhook
   ```

3. **Verify in ARRMS**:
   - Check if the record was created/updated in ARRMS
   - Verify data transformation is correct

## Alternative: Environment Variable (Optional)

If you have a **single** primary Onspring application, you can set a default App ID:

### Update CloudFormation Stack

```bash
aws cloudformation update-stack \
  --stack-name arrms-onspring-integration-dev \
  --use-previous-template \
  --parameters \
    ParameterKey=OnspringDefaultAppId,ParameterValue=100 \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=OnspringApiUrl,UsePreviousValue=true \
    ParameterKey=OnspringApiKeySecretName,UsePreviousValue=true \
    ParameterKey=ArrmsApiUrl,UsePreviousValue=true \
    ParameterKey=ArrmsApiKeySecretName,UsePreviousValue=true \
    ParameterKey=LogLevel,UsePreviousValue=true \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Then Use Simpler URL

If default App ID is set, you can omit the query parameter:
```
https://tfyp2toag2.execute-api.us-east-1.amazonaws.com/dev/webhook/onspring
```

**Note**: Query parameter `?appId=XXX` always overrides the environment variable if provided.

## Payload Format

### What Onspring Sends

```json
[{"RecordId": "16"}]
```

### What the Lambda Does

1. **Parse payload**: Extract `RecordId` from array
2. **Get appId**: From query parameter `?appId=XXX` or environment variable
3. **Fetch full record**: Call `GET /v2/Records/{recordId}` on Onspring API
4. **Transform data**: Convert Onspring format to ARRMS format
5. **Upsert to ARRMS**: Create or update record in ARRMS

## Multiple Applications

If you have multiple Onspring applications (e.g., Risks, Controls, Incidents):

1. Configure **separate workflows** in each application
2. Use the **same webhook URL** but with different `appId` parameters:
   - Risks: `.../webhook/onspring?appId=100`
   - Controls: `.../webhook/onspring?appId=101`
   - Incidents: `.../webhook/onspring?appId=102`

The Lambda function will fetch records from the correct application based on the `appId`.

## Troubleshooting

### Error: "Missing appId - include ?appId=XXX in webhook URL"

**Solution**: Add the `appId` query parameter to your webhook URL:
```
?appId=100
```

### Error: "Missing required field: RecordId"

**Solution**: Verify your Onspring body template uses:
```json
[{"RecordId": "[RecordId]"}]
```

### Error: "Forbidden" (403)

**Solution**: Check that you've added the API key header:
- Header: `x-api-key`
- Value: `qx5Y2ookMbSJfERExOF427sfl2OKnTT74eRlBjc0`

### Records Not Syncing to ARRMS

**Check**:
1. CloudWatch Logs for errors
2. ARRMS API URL is correct (not placeholder)
3. ARRMS API key is valid in Secrets Manager
4. Data transformation logic in `src/handlers/onspring_webhook.py`

### Test Locally

Test the Lambda function with your payload:

```bash
# Create test event
cat > test-event.json << 'EOF'
{
  "body": "[{\"RecordId\": \"16\"}]",
  "queryStringParameters": {"appId": "100"}
}
EOF

# Invoke locally
sam local invoke OnspringWebhookFunction -e test-event.json
```

## Data Transformation

The default transformation is a passthrough. Customize it in:
- **File**: `src/handlers/onspring_webhook.py`
- **Function**: `transform_onspring_to_arrms()`

Example:

```python
def transform_onspring_to_arrms(onspring_data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform Onspring record to ARRMS format."""

    # Extract fields from Onspring response
    record_id = onspring_data.get("recordId")
    fields = onspring_data.get("fieldData", [])

    # Build field map
    field_map = {field.get("fieldId"): field.get("value") for field in fields}

    # Transform to ARRMS format
    return {
        "id": record_id,
        "name": field_map.get(1234),  # Field ID 1234 = Name
        "description": field_map.get(1235),  # Field ID 1235 = Description
        "status": field_map.get(1236),  # Field ID 1236 = Status
        "severity": field_map.get(1237),  # Field ID 1237 = Severity
        "source": "onspring",
        "onspring_app_id": onspring_data.get("appId")
    }
```

## Best Practices

1. **Start with One Workflow**: Test with a single workflow before configuring multiple
2. **Use Specific Conditions**: Don't trigger on every field change - be selective
3. **Monitor Logs**: Watch CloudWatch Logs during initial setup
4. **Test Thoroughly**: Use Onspring's "Test Request" before going live
5. **Document App IDs**: Keep a record of which App ID corresponds to which application

## Next Steps

1. Configure your Onspring REST API Outcome using the steps above
2. Test with a sample record
3. Verify data appears in ARRMS
4. Customize data transformation as needed
5. Roll out to additional workflows/applications

## Support

- **CloudWatch Logs**: `/aws/lambda/arrms-onspring-integration-dev-onspring-webhook`
- **GitHub Issues**: https://github.com/Beleza-Asureti/arrms-onspring-integration/issues
- **Documentation**: See `/docs` directory
