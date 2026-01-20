# Data Contract: ARRMS-Onspring Integration

This document defines the data contract between Onspring (GRC system) and ARRMS (Risk & Resilience Management System). It specifies field mappings, expected payloads, transformation rules, and business logic.

## Overview

```
┌─────────────┐         ┌─────────────────────┐         ┌─────────────┐
│  Onspring   │ ──────► │  Integration Layer  │ ──────► │    ARRMS    │
│  (Source)   │ ◄────── │    (AWS Lambda)     │ ◄────── │  (Target)   │
└─────────────┘         └─────────────────────┘         └─────────────┘
```

**Data Flows:**
1. **Onspring → ARRMS**: Questionnaire files and metadata sync
2. **ARRMS → Onspring**: Statistics and status updates

---

## 1. Onspring → Integration

### 1.1 Webhook Payload (REST API Outcome)

Onspring triggers webhooks via REST API Outcomes in workflows.

**Endpoint:** `POST /webhook/onspring`

**Headers:**
| Header | Value | Required |
|--------|-------|----------|
| `Content-Type` | `application/json` | Yes |
| `x-api-key` | API Gateway key | Yes |

**Payload Format:**
```json
[
  {
    "RecordId": "12345",
    "AppId": "248"
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `RecordId` | string | Yes | Onspring record identifier |
| `AppId` | string | Yes | Onspring application identifier |

### 1.2 Onspring Record Structure

After receiving the webhook, the integration fetches the full record from Onspring API.

**Onspring API Response:** `GET /Records/appId/{appId}/recordId/{recordId}`

```json
{
  "appId": 248,
  "recordId": 12345,
  "fieldData": [
    {"fieldId": 14872, "type": "Date", "value": "2026-03-31"},
    {"fieldId": 14888, "type": "String", "value": "SOC 2 Type II scope description"},
    {"fieldId": 14947, "type": "Integer", "value": 501},
    {"fieldId": 15083, "type": "String", "value": null},
    {
      "fieldId": 200,
      "type": "FileList",
      "value": [
        {
          "fileId": 5001,
          "fileName": "questionnaire.xlsx",
          "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
      ]
    }
  ]
}
```

**Onspring Input Field IDs (App 248):**

| Field ID | Field Name | Type | Maps To (ARRMS) |
|----------|------------|------|-----------------|
| 14872 | Request Due Back to External Requestor | Date | `due_date` |
| 14888 | Scope Summary | String | `notes` |
| 14947 | External Requestor Company Name | Reference (App 249) | `requester_name` (resolved) |
| 15083 | Questionnaire Link | String | *Written back by integration* |
| 200 | Attachments | FileList | Questionnaire file |

**Reference Field Resolution:**

Field 14947 is a reference to App 249 (Companies). The integration resolves it by:
1. Reading the record ID from field 14947
2. Fetching field 14949 from App 249 using that record ID
3. Using the resolved value as `requester_name`

### 1.3 File Attachment Handling

Files are downloaded separately via the Onspring Files API.

**Download Endpoint:** `GET /Files/recordId/{recordId}/fieldId/{fieldId}/fileId/{fileId}/file`

| Parameter | Description |
|-----------|-------------|
| `recordId` | Onspring record ID |
| `fieldId` | Field ID of the attachment field |
| `fileId` | Individual file identifier |

**Supported File Types:**
- Excel: `.xlsx`, `.xls`
- PDF: `.pdf`
- Word: `.docx`, `.doc`

---

## 2. Integration → ARRMS

### 2.1 Questionnaire Upload

**Endpoint:** `POST /api/v1/integrations/questionnaires/upload`

**Content-Type:** `multipart/form-data`

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | Yes | Questionnaire file (Excel format) |
| `external_id` | string | Yes | Onspring record ID |
| `external_source` | string | Yes | Always `"onspring"` |
| `external_metadata` | JSON string | No | Additional metadata from Onspring |

**Example Request:**
```
POST /api/v1/integrations/questionnaires/upload
Content-Type: multipart/form-data

file: [binary content]
external_id: "12345"
external_source: "onspring"
external_metadata: {"app_id": 248, "onspring_url": "https://app.onspring.com/record/12345"}
```

**Response:**
```json
{
  "id": "uuid-questionnaire-id",
  "name": "SOC 2 Assessment",
  "status": "processing",
  "external_references": [
    {
      "id": "uuid-ref-id",
      "external_id": "12345",
      "external_source": "onspring",
      "external_metadata": {
        "app_id": 248,
        "onspring_url": "https://app.onspring.com/record/12345"
      },
      "sync_status": null,
      "last_synced_at": null
    }
  ],
  "created_at": "2026-01-19T10:30:00Z"
}
```

### 2.2 Find Existing Questionnaire

Prevents duplicate creation when re-syncing.

**Endpoint:** `GET /api/v1/integrations/questionnaires/find`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `external_id` | string | Yes | Onspring record ID |
| `external_source` | string | Yes | Always `"onspring"` |

**Response (if found):**
```json
{
  "id": "uuid-questionnaire-id",
  "name": "SOC 2 Assessment",
  "external_references": [...]
}
```

**Response (if not found):** HTTP 404

### 2.3 Update Questionnaire File

Updates the source file for an existing questionnaire.

**Endpoint:** `PUT /api/v1/integrations/questionnaires/{questionnaire_id}/file`

**Content-Type:** `multipart/form-data`

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | Yes | New questionnaire file |
| `external_metadata` | JSON string | No | Updated metadata |

### 2.4 Upload Additional Documents

Attaches supporting documents to a questionnaire.

**Endpoint:** `POST /api/v1/questionnaires/{questionnaire_id}/documents`

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | Yes | Document file |
| `external_id` | string | No | Onspring file ID |
| `external_source` | string | Yes | Always `"onspring"` |
| `source_metadata` | JSON string | No | Onspring file metadata |

---

## 3. ARRMS → Integration

### 3.1 Questionnaire Statistics

The integration polls ARRMS for statistics to sync back to Onspring.

**Endpoint:** `GET /api/v1/integrations/questionnaires/{external_id}/statistics`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `external_source` | string | Yes | Always `"onspring"` |

**Response:**
```json
{
  "id": "uuid-questionnaire-id",
  "external_id": "12345",
  "summary": {
    "total_questions": 150,
    "answered_questions": 120,
    "approved_questions": 100,
    "unanswered_questions": 30,
    "confidence_distribution": {
      "very_high": 45,
      "high": 30,
      "medium": 15,
      "low": 10
    }
  },
  "metadata": {
    "source_document": {
      "url": "https://arrms.example.com/documents/abc123.pdf",
      "generated_at": "2026-01-19T12:00:00Z"
    }
  },
  "questions": [
    {
      "id": "q-uuid-1",
      "text": "Describe your access control policy",
      "status": "approved",
      "confidence": 0.92
    }
  ]
}
```

### 3.2 Statistics Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `summary.total_questions` | integer | Total questions in questionnaire |
| `summary.answered_questions` | integer | Questions with AI-generated responses |
| `summary.approved_questions` | integer | Questions with approved responses |
| `summary.unanswered_questions` | integer | Questions without responses |
| `summary.confidence_distribution.very_high` | integer | Questions with >80% confidence |
| `summary.confidence_distribution.high` | integer | Questions with 50-80% confidence |
| `summary.confidence_distribution.medium` | integer | Questions with 25-50% confidence |
| `summary.confidence_distribution.low` | integer | Questions with <25% confidence |
| `metadata.source_document.url` | string | URL to generated output document |

---

## 4. Integration → Onspring

### 4.1 Questionnaire Link Write-back

After creating/updating a questionnaire in ARRMS, the integration writes the questionnaire link back to Onspring.

**Endpoint:** `PUT /Records`

**Field:** 15083 (Questionnaire Link)

**Value Format:**
```
{ARRMS_API_URL}/questionnaire-answers?questionnaire={questionnaire_id}
```

**Example:**
```
https://demo.preview.asureti.com/questionnaire-answers?questionnaire=abc123-def456
```

### 4.2 Statistics Field Update Payload

The integration updates Onspring records with ARRMS statistics.

**Endpoint:** `PUT /Records`

**Request:**
```json
{
  "appId": 248,
  "recordId": 12345,
  "fields": {
    "14932": 150,
    "14934": 100,
    "14933": 50,
    "14936": 45,
    "14937": 30,
    "14938": 15,
    "14939": 10,
    "14906": "30733b38-2b9b-43a6-ade5-d7f0b69ba6b2"
  }
}
```

### 4.3 Field Mapping Table

| Onspring Field Name | Field ID | Type | Source (ARRMS) | Transformation |
|---------------------|----------|------|----------------|----------------|
| Questionnaire Link | 15083 | String | ARRMS questionnaire ID | URL construction |
| Total Assessment Questions | 14932 | Integer | `summary.total_questions` | Direct |
| Complete Assessment Questions | 14934 | Integer | `summary.approved_questions` | Direct |
| Open Assessment Questions | 14933 | Integer | *Calculated* | `total - complete` |
| High Confidence Questions | 14936 | Integer | `confidence_distribution.very_high` | Direct |
| Medium-High Confidence | 14937 | Integer | `confidence_distribution.high` | Direct |
| Medium-Low Confidence | 14938 | Integer | `confidence_distribution.medium` | Direct |
| Low Confidence Questions | 14939 | Integer | `confidence_distribution.low` | Direct |
| Status (Agentic Status) | 14906 | List (UUID) | *Calculated* | See Status Logic |

> **Note:** Field IDs are specific to App ID 248 (demo environment). Production deployments should configure field mappings via the `ONSPRING_FIELD_MAPPING` environment variable.

### 4.4 Confidence Level Mapping

| ARRMS Confidence | Percentage Range | Onspring Field |
|------------------|------------------|----------------|
| `very_high` | >80% | High Confidence Questions |
| `high` | 50-80% | Medium-High Confidence |
| `medium` | 25-50% | Medium-Low Confidence |
| `low` | <25% | Low Confidence Questions |

---

## 5. Business Logic & Transformation Rules

### 5.1 Status Calculation

The "Agentic Status" field is calculated based on ARRMS progress:

```
IF answered_questions == 0:
    status = "Not Started"
ELIF approved_questions == total_questions AND has_document:
    status = "Ready for Validation"
ELSE:
    status = "Request in Process"
```

### 5.2 Status List Value IDs

Onspring list fields use UUIDs, not text strings:

| Status Text | List Value UUID |
|-------------|-----------------|
| Not Started | `61be3f2e-d333-4983-b503-4b198622a1c2` |
| Request in Process | `cdae7799-07e1-472d-b8f6-1a70f50305e8` |
| Ready for Validation | `30733b38-2b9b-43a6-ade5-d7f0b69ba6b2` |

> **Note:** UUIDs are specific to App ID 248, Field ID 14906. Other Onspring apps will have different UUIDs.

### 5.3 Open Questions Calculation

"Open Assessment Questions" is **calculated**, not sourced directly from ARRMS:

```python
open_questions = total_questions - complete_questions
```

Where:
- `total_questions` = `summary.total_questions`
- `complete_questions` = `summary.approved_questions`

This ensures accuracy even if the ARRMS `unanswered_questions` field is missing.

### 5.4 External ID Format

The `external_id` may include a prefix:

| Format | Example | Parsed Record ID |
|--------|---------|------------------|
| Plain | `12345` | `12345` |
| Prefixed | `onspring-12345` | `12345` |

---

## 6. Error Handling

### 6.1 Validation Errors (HTTP 400)

| Error | Cause |
|-------|-------|
| `Missing required field: RecordId` | Webhook payload missing RecordId |
| `Missing AppId` | No AppId in payload or environment |
| `No files found for record` | Onspring record has no attachments |
| `Questionnaire file has no extension` | File missing extension |

### 6.2 Integration Errors (HTTP 502/503)

| Error | Cause |
|-------|-------|
| `Failed to upload questionnaire` | ARRMS API error |
| `Failed to fetch statistics` | ARRMS statistics endpoint error |
| `Failed to update Onspring record` | Onspring API error |

### 6.3 Retry Strategy

- **Retries:** 3 attempts
- **Backoff:** Exponential (1s, 2s, 4s)
- **Retry on:** HTTP 429, 500, 502, 503, 504

---

## 7. Environment Configuration

### 7.1 Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ARRMS_API_URL` | ARRMS API base URL | `https://api.arrms.example.com` |
| `ARRMS_API_KEY_SECRET` | AWS Secrets Manager secret name | `arrms/api-key/prod` |
| `ONSPRING_API_URL` | Onspring API base URL | `https://api.onspring.com` |
| `ONSPRING_API_KEY_SECRET` | AWS Secrets Manager secret name | `onspring/api-key/prod` |
| `ONSPRING_DEFAULT_APP_ID` | Default Onspring App ID | `248` |

### 7.2 Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ONSPRING_FIELD_MAPPING` | JSON mapping of field names to IDs | Hardcoded demo values |

**Example `ONSPRING_FIELD_MAPPING`:**
```json
{
  "Total Assessment Questions": 14932,
  "Complete Assessment Questions": 14934,
  "Open Assessment Questions": 14933,
  "High Confidence Questions": 14936,
  "Medium-High Confidence": 14937,
  "Medium-Low Confidence": 14938,
  "Low Confidence Questions": 14939,
  "Status": 14906
}
```

---

## 8. Sample Payloads

### 8.1 Complete Webhook Flow

**Step 1: Onspring sends webhook**
```json
[{"RecordId": "12345", "AppId": "248"}]
```

**Step 2: Integration fetches record from Onspring**
```json
{
  "appId": 248,
  "recordId": 12345,
  "fieldData": [
    {"fieldId": 14904, "type": "FileList", "value": [{"fileId": 5001, "fileName": "questionnaire.xlsx"}]}
  ]
}
```

**Step 3: Integration uploads to ARRMS**
```
POST /api/v1/integrations/questionnaires/upload
file: questionnaire.xlsx
external_id: "12345"
external_source: "onspring"
```

**Step 4: ARRMS returns questionnaire ID**
```json
{"id": "q-uuid-123", "external_references": [{"external_id": "12345"}]}
```

### 8.2 Statistics Sync Flow

**Step 1: Integration fetches statistics from ARRMS**
```json
{
  "summary": {
    "total_questions": 150,
    "approved_questions": 100,
    "confidence_distribution": {"very_high": 45, "high": 30, "medium": 15, "low": 10}
  },
  "metadata": {"source_document": {"url": "https://..."}}
}
```

**Step 2: Integration calculates Onspring fields**
```json
{
  "Total Assessment Questions": 150,
  "Complete Assessment Questions": 100,
  "Open Assessment Questions": 50,
  "High Confidence Questions": 45,
  "Medium-High Confidence": 30,
  "Medium-Low Confidence": 15,
  "Low Confidence Questions": 10,
  "Status": "30733b38-2b9b-43a6-ade5-d7f0b69ba6b2"
}
```

**Step 3: Integration updates Onspring record**
```json
{
  "appId": 248,
  "recordId": 12345,
  "fields": {
    "14932": 150,
    "14934": 100,
    "14933": 50,
    "14936": 45,
    "14937": 30,
    "14938": 15,
    "14939": 10,
    "14906": "30733b38-2b9b-43a6-ade5-d7f0b69ba6b2"
  }
}
```

---

## 9. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-19 | Initial data contract |

---

## 10. Related Documentation

- [Architecture Overview](./ARCHITECTURE.md)
- [Onspring Setup Guide](./ONSPRING_SETUP.md)
- [Onspring API Spec](./swagger.json)
- [Deployment Guide](./DEPLOYMENT.md)
