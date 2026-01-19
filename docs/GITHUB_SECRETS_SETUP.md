# GitHub Secrets Setup for Deployment

This document explains how to configure the required GitHub repository secrets for automated deployment.

## Required Secrets

Navigate to your GitHub repository: **Settings > Secrets and variables > Actions > New repository secret**

### 1. ONSPRING_API_URL
- **Value**: Your Onspring API base URL
- **Example**: `https://api.onspring.com`

### 2. ONSPRING_DEFAULT_APP_ID
- **Value**: The numeric ID of your Onspring GRC application
- **Example**: `12345`
- **How to find**:
  - Log into Onspring
  - Navigate to your GRC application
  - Check the URL - it will be `https://yourinstance.onspring.com/Admin/App/View/{AppId}`
  - Or use the Onspring API to list your apps

### 3. ONSPRING_FIELD_MAPPING
- **Value**: JSON object mapping field names to field IDs
- **Format**: Must be valid JSON (compact, no line breaks)
- **Example**:
  ```json
  {"Total Assessment Questions":12345,"Complete Assessment Questions":12346,"Open Assessment Questions":12347,"High Confidence Questions":12348,"Medium-High Confidence":12349,"Medium-Low Confidence":12350,"Low Confidence Questions":12351,"Status":12352}
  ```

#### How to Find Onspring Field IDs

**Option 1: Using Onspring UI**
1. Log into Onspring
2. Go to your GRC application
3. Navigate to **Administration > Fields**
4. Click on each field to view its properties
5. The Field ID will be shown in the field details

**Option 2: Using Onspring API**
```bash
# Get all fields for your app
curl -X GET "https://api.onspring.com/Fields/appId/{YOUR_APP_ID}" \
  -H "X-ApiKey: YOUR_API_KEY" \
  -H "Content-Type: application/json"
```

**Option 3: Create a helper script**

Create a file `scripts/get_onspring_fields.py`:
```python
#!/usr/bin/env python3
import json
import os
from adapters.onspring_client import OnspringClient

# Initialize client
client = OnspringClient(
    api_url=os.environ.get("ONSPRING_API_URL"),
    api_key=os.environ.get("ONSPRING_API_KEY")
)

# Get fields for your app
app_id = int(input("Enter your Onspring App ID: "))
# Use client methods to fetch fields and print the mapping

print("Field mapping for GitHub secret:")
# Print the JSON mapping
```

### 4. ARRMS_API_URL
- **Value**: Your ARRMS API base URL
- **Example**: `https://arrms.yourdomain.com`
- **For dev/testing**: Your local/dev ARRMS instance URL

## Step-by-Step Setup

1. **Go to GitHub Repository Settings**
   ```
   https://github.com/Beleza-Asureti/arrms-onspring-integration/settings/secrets/actions
   ```

2. **Click "New repository secret"**

3. **Add each secret one by one:**
   - Name: `ONSPRING_API_URL`
   - Value: `https://api.onspring.com`
   - Click "Add secret"

4. **Repeat for all required secrets:**
   - `ONSPRING_DEFAULT_APP_ID` → Your app ID (e.g., `12345`)
   - `ONSPRING_FIELD_MAPPING` → Your JSON mapping (compact, no spaces)
   - `ARRMS_API_URL` → Your ARRMS API URL

## Verification

After adding all secrets:

1. Go to **Actions** tab in your repository
2. Click on the latest workflow run
3. Check the deployment logs to verify parameters are being passed correctly
4. Look for the "Deploy to AWS" step - it should show all parameter overrides

## Updating Field Mapping

When you need to update the field mapping:

1. Go to repository **Settings > Secrets and variables > Actions**
2. Find `ONSPRING_FIELD_MAPPING`
3. Click the pencil icon to edit
4. Update the JSON value
5. Click "Update secret"
6. Re-run the deployment workflow

## Troubleshooting

### "ONSPRING_DEFAULT_APP_ID not configured" error
- Check that the secret is named exactly `ONSPRING_DEFAULT_APP_ID` (case-sensitive)
- Verify the value is a number, not empty

### "Invalid ONSPRING_DEFAULT_APP_ID" error
- The value must be numeric only (no quotes, no spaces)
- Example: `12345` not `"12345"`

### Field mapping errors
- Ensure the JSON is valid (use a JSON validator)
- Remove all line breaks and extra spaces
- Use double quotes for keys and string values
- Example: `{"Field Name":123}` not `{'Field Name':123}`

### Secrets not being picked up
- Secret names are case-sensitive
- Secrets are only available to workflows after being added
- Re-run the workflow after adding/updating secrets
