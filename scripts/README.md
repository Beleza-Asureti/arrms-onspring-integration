# Local Development Scripts

This directory contains scripts for running the ARRMS integration locally without AWS dependencies.

## Quick Start

1. **Copy the environment template:**
   ```bash
   cp .env.local.template .env.local
   ```

2. **Edit `.env.local` with your ARRMS credentials:**
   ```
   ARRMS_API_URL=https://your-arrms-instance.com
   ARRMS_API_KEY=your-api-key
   ```

3. **Run the local runner:**
   ```bash
   python scripts/local_runner.py
   ```

## What This Does

The local runner:
- **Mocks Onspring** - Uses `MockOnspringClient` to simulate Onspring API responses
- **Real ARRMS calls** - Makes actual HTTP requests to your ARRMS instance
- **Detailed logging** - Logs all HTTP request/response details for debugging

## Usage Examples

```bash
# Health check only
python scripts/local_runner.py --health-check

# Simulate single webhook (default record ID 12345)
python scripts/local_runner.py --webhook

# Simulate webhook for specific record
python scripts/local_runner.py --webhook --record-id 99999

# Simulate batch sync
python scripts/local_runner.py --batch --batch-size 5

# Use different env file
python scripts/local_runner.py --env-file .env.staging

# Disable request/response body logging
python scripts/local_runner.py --no-log-bodies
```

## Files

- `local_runner.py` - Main entry point
- `mock_onspring.py` - Mock Onspring client and sample data
- `sample_files/` - Sample questionnaire files for testing

## Sample Files

Place your own test files in `sample_files/`:
- `sample_questionnaire.xlsx` - Sample Excel questionnaire (included)

The mock client will use files from this directory when simulating file downloads from Onspring.

## Customizing Mock Data

Edit `mock_onspring.py` to customize the mock Onspring records:

```python
MOCK_RECORDS = [
    {
        "recordId": 12345,
        "appId": 100,
        "fields": {
            "Title": {"value": "Your Title", "fieldId": 101},
            # ... add more fields
        },
        "fieldData": [
            # ... file attachments
        ]
    }
]
```

## HTTP Logging Output

The local runner logs detailed HTTP traffic:

```
================================================================================
REQUEST #1: POST https://demo.preview.asureti.com/api/v1/integrations/questionnaires/upload
================================================================================
Headers: {
  "X-API-Key": "***",
  "Accept": "application/json"
}
Form Data:
{
  "external_id": "12345",
  "external_source": "onspring",
  ...
}
File 'file': sample_questionnaire.xlsx (application/vnd..., 15234 bytes)
--------------------------------------------------------------------------------
RESPONSE: 201 Created
--------------------------------------------------------------------------------
Response JSON:
{
  "id": "abc123",
  "name": "Sample Questionnaire",
  ...
}
================================================================================
```

## Troubleshooting

**"ARRMS_API_KEY not set"**
- Make sure `.env.local` exists and has the `ARRMS_API_KEY` value set

**Connection errors**
- Verify `ARRMS_API_URL` is correct and accessible
- Check if you need VPN access

**401 Unauthorized**
- Verify your API key is correct
- Check if the API key has the required permissions
