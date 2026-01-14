# Architecture Documentation

## System Overview

The ARRMS-Onspring Integration Service is a serverless integration platform built on AWS Lambda that enables decoupled, bi-directional data synchronization between Onspring (GRC system of record) and ARRMS (Risk & Resilience Management System).

## Design Principles

### 1. Loose Coupling
- Onspring and ARRMS remain independent systems
- Integration service acts as the only integration boundary
- No shared state or direct dependencies between source systems

### 2. Stateless Execution
- Lambda functions are stateless
- No local storage dependencies
- Configuration via environment variables and Secrets Manager

### 3. Event-Driven Architecture
- Webhook-based real-time integration
- Scheduled batch processing for bulk sync
- Asynchronous processing where appropriate

### 4. Security First
- API Key authentication at API Gateway
- Secrets stored in AWS Secrets Manager
- IAM least-privilege permissions
- HTTPS-only communication

### 5. Observability
- Structured logging with AWS Lambda Powertools
- CloudWatch metrics for operational monitoring
- X-Ray distributed tracing
- Health check endpoints

## Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Cloud                                │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │              API Gateway                            │    │
│  │  - API Key Authentication                          │    │
│  │  - Rate Limiting & Throttling                      │    │
│  │  - CORS Configuration                              │    │
│  └──────┬─────────────────┬──────────────┬───────────┘    │
│         │                 │              │                 │
│         ▼                 ▼              ▼                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐       │
│  │  Webhook    │  │  Sync        │  │  Health    │       │
│  │  Handler    │  │  Handler     │  │  Check     │       │
│  │  Lambda     │  │  Lambda      │  │  Lambda    │       │
│  └──────┬──────┘  └──────┬───────┘  └────────────┘       │
│         │                 │                                │
│         └────────┬────────┘                                │
│                  │                                         │
│         ┌────────▼────────┐                                │
│         │   Adapters      │                                │
│         │  ┌────────────┐ │                                │
│         │  │ Onspring   │ │                                │
│         │  │ Client     │ │                                │
│         │  └────────────┘ │                                │
│         │  ┌────────────┐ │                                │
│         │  │   ARRMS    │ │                                │
│         │  │  Client    │ │                                │
│         │  └────────────┘ │                                │
│         └─────────────────┘                                │
│                  │                                         │
│         ┌────────▼────────┐                                │
│         │  AWS Services   │                                │
│         │  - Secrets Mgr  │                                │
│         │  - CloudWatch   │                                │
│         │  - X-Ray        │                                │
│         └─────────────────┘                                │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────┐
│   Onspring      │          │      ARRMS       │
│   (External)    │          │   (External)     │
└─────────────────┘          └──────────────────┘
```

## Data Flow

### Webhook Flow (Real-time)

1. **Event Trigger**: Onspring sends webhook POST to API Gateway
2. **Authentication**: API Gateway validates API key
3. **Lambda Invocation**: Webhook handler Lambda is invoked
4. **Event Processing**:
   - Parse webhook payload
   - Validate event data
   - Retrieve full record from Onspring (if needed)
5. **Data Transformation**: Convert Onspring format to ARRMS format
6. **ARRMS Update**: Push transformed data to ARRMS API
7. **Response**: Return success/failure to Onspring

```
Onspring → API Gateway → Lambda → Onspring API (fetch) → Transform → ARRMS API
                                        ↓
                                   CloudWatch Logs
                                   CloudWatch Metrics
```

### Sync Flow (Scheduled/On-Demand)

1. **Trigger**: API call or EventBridge schedule
2. **Authentication**: API Gateway validates API key
3. **Lambda Invocation**: Sync handler Lambda is invoked
4. **Batch Retrieval**:
   - Query Onspring for records (with filters)
   - Paginate through results
5. **Batch Processing**:
   - Transform each record
   - Upsert to ARRMS (create or update)
   - Track successes and failures
6. **Response**: Return summary statistics

```
Trigger → API Gateway → Lambda → Onspring API (query) → Transform → ARRMS API (batch)
                                        ↓
                                   CloudWatch Logs
                                   CloudWatch Metrics
```

## API Design

### RESTful Endpoints

#### POST /webhook/onspring
- **Purpose**: Receive real-time events from Onspring
- **Auth**: API Key
- **Idempotency**: Event ID can be used for deduplication
- **Timeout**: 60 seconds

#### POST /sync/onspring-to-arrms
- **Purpose**: Trigger manual or scheduled sync
- **Auth**: API Key
- **Parameters**: app_id, filter, batch_size
- **Timeout**: 300 seconds (5 minutes)

#### GET /health
- **Purpose**: Health monitoring
- **Auth**: API Key
- **Response**: Service status and dependency checks
- **Timeout**: 30 seconds

## Error Handling Strategy

### Error Categories

1. **Validation Errors** (4xx)
   - Missing required fields
   - Invalid data format
   - Bad request structure

2. **Authentication Errors** (401/403)
   - Missing or invalid API key
   - Secrets Manager access denied

3. **Integration Errors** (502/503)
   - Onspring API unavailable
   - ARRMS API unavailable
   - Network timeouts

4. **System Errors** (500)
   - Unexpected exceptions
   - Lambda runtime errors

### Retry Strategy

- **HTTP Retries**: 3 attempts with exponential backoff
- **Status Codes**: Retry on 429, 500, 502, 503, 504
- **Backoff Factor**: 1 second base
- **Max Backoff**: 10 seconds

### Error Logging

All errors logged with:
- Error type and message
- Request context
- Stack trace (for unexpected errors)
- Correlation ID (for tracing)

## Security Architecture

### Authentication & Authorization

```
Request → API Gateway (API Key) → Lambda (IAM Role) → Secrets Manager
                                                     → External APIs
```

1. **API Gateway**: API Key validation
2. **Lambda Execution Role**: IAM permissions
3. **Secrets Manager**: API key storage
4. **External APIs**: Bearer token or API key

### Secrets Management

- Onspring API Key: Stored in Secrets Manager
- ARRMS API Key: Stored in Secrets Manager
- Retrieved at runtime via boto3
- Cached in Lambda execution context

### Network Security

- All external calls over HTTPS
- No public inbound access to Lambda
- API Gateway as single entry point
- VPC deployment optional (not required for basic setup)

## Scalability

### Lambda Concurrency

- **Default**: Account-level concurrency limit
- **Reserved**: Can configure per-function reserved concurrency
- **Provisioned**: Optional for predictable workloads

### API Gateway Limits

- **Throttle**: 50 requests/second (configurable)
- **Burst**: 100 concurrent requests
- **Daily Quota**: 10,000 requests (configurable)

### Batch Processing

- **Page Size**: 100 records (configurable)
- **Timeout**: 5 minutes for sync operations
- **Pagination**: Automatic for large datasets

## Monitoring & Alerting

### CloudWatch Metrics

Custom metrics:
- `WebhookReceived`
- `WebhookProcessed`
- `WebhookValidationError`
- `WebhookIntegrationError`
- `RecordsRetrieved`
- `RecordsSyncedSuccessfully`
- `RecordsSyncedFailed`

Standard Lambda metrics:
- Invocations
- Duration
- Errors
- Throttles

### CloudWatch Alarms (Recommended)

1. **High Error Rate**: >5% error rate over 5 minutes
2. **Integration Failures**: Any integration error
3. **High Latency**: P99 duration >30 seconds
4. **Throttling**: Any throttled requests

### X-Ray Tracing

- End-to-end request tracing
- Service map visualization
- Performance bottleneck identification
- Error rate by service

## Deployment Architecture

### Environments

- **Dev**: Development and testing
- **Staging**: Pre-production validation
- **Prod**: Production workloads

### Infrastructure as Code

AWS SAM template defines:
- API Gateway configuration
- Lambda functions
- IAM roles and policies
- CloudWatch Log Groups
- Environment-specific parameters

### Deployment Process

1. **Build**: `sam build`
2. **Validate**: `sam validate`
3. **Deploy**: `sam deploy --guided`
4. **Test**: Invoke with sample events
5. **Monitor**: Check CloudWatch Logs and Metrics

## Data Model

### Onspring Record Structure (Example)

```json
{
  "recordId": 12345,
  "appId": 100,
  "fields": {
    "Name": "Risk Name",
    "Description": "Description",
    "Status": "Open",
    "Severity": "High"
  }
}
```

### ARRMS Record Structure (Example)

```json
{
  "id": 12345,
  "name": "Risk Name",
  "description": "Description",
  "status": "open",
  "severity": "high",
  "source": "onspring",
  "synced_at": "2024-01-15T10:30:00Z"
}
```

### Transformation Logic

Implemented in handler functions:
- Field name mapping
- Value normalization
- Type conversion
- Validation

## Performance Considerations

### Lambda Optimization

- **Memory**: 512MB (adjustable based on workload)
- **Timeout**: 60s (webhook), 300s (sync)
- **Cold Start**: ~1-2 seconds
- **Warm Execution**: ~100-500ms

### API Performance

- **Onspring API**: Rate limits per API key
- **ARRMS API**: Rate limits per API key
- **Retry Logic**: Prevents overload

### Caching Strategy

- Lambda execution context reuse
- API clients cached across invocations
- Secrets cached in memory (refreshed periodically)

## Future Enhancements

1. **Bi-directional Sync**: ARRMS → Onspring
2. **DynamoDB Integration**: Field mapping configuration
3. **SQS Queue**: Decouple webhook processing
4. **Dead Letter Queue**: Failed event retention
5. **Step Functions**: Complex orchestration
6. **EventBridge**: Event routing and filtering
7. **API Versioning**: Support multiple API versions
8. **Field Mapping UI**: Dynamic configuration

## Disaster Recovery

### Backup Strategy

- Lambda code: Stored in S3 by SAM
- Configuration: Version controlled in Git
- Secrets: Backup via Secrets Manager replication

### Recovery Procedures

1. Redeploy from SAM template
2. Restore secrets if needed
3. Verify API Gateway endpoints
4. Test with sample events

### RTO/RPO

- **RTO**: <1 hour (redeployment time)
- **RPO**: Near-zero (stateless architecture)

## Compliance

- API keys stored securely
- Audit logging via CloudWatch
- Encryption at rest (Secrets Manager)
- Encryption in transit (HTTPS)
- IAM least-privilege access
