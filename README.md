# ARRMS-Onspring Integration Service

AWS Lambda-based integration service that enables bi-directional, decoupled integration between Onspring (GRC source of record) and ARRMS (Asureti Risk & Resilience Management System).

## Overview

This service acts as a translation layer and integration boundary between Onspring and ARRMS, ensuring both systems remain loosely coupled while maintaining data synchronization through well-defined API contracts.

### Key Features

- **Event-Driven Integration**: Webhook receiver for real-time Onspring events
- **Scheduled Sync**: Periodic batch synchronization from Onspring to ARRMS
- **RESTful API**: Secure API Gateway endpoints with API Key authentication
- **Serverless Architecture**: AWS Lambda for stateless, scalable execution
- **Structured Logging**: AWS Lambda Powertools for observability
- **Error Handling**: Comprehensive error handling with retry logic
- **Health Monitoring**: Health check endpoints for operational monitoring

## Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌──────────┐
│  Onspring  │────────▶│  API Gateway     │────────▶│  ARRMS   │
│             │  Events │  + Lambda        │  Push   │          │
│  (Source)   │────────▶│  Integration     │────────▶│ (Target) │
└─────────────┘         └──────────────────┘         └──────────┘
                              │
                              │ Secrets Manager
                              ▼
                        ┌──────────────┐
                        │  API Keys    │
                        │  Config      │
                        └──────────────┘
```

### Components

1. **API Gateway**: Exposes RESTful endpoints with API Key authentication
2. **Lambda Functions**:
   - `onspring-webhook`: Receives and processes webhook events
   - `onspring-to-arrms`: Retrieves and syncs data from Onspring to ARRMS
   - `health-check`: Provides health status for monitoring
3. **Adapters**:
   - `OnspringClient`: Handles Onspring API interactions
   - `ARRMSClient`: Handles ARRMS API interactions
4. **Utilities**: Logging, error handling, response formatting

## Prerequisites

- Python 3.11+
- AWS CLI configured with appropriate credentials
- AWS SAM CLI (`pip install aws-sam-cli`)
- Access to AWS account with permissions for:
  - Lambda
  - API Gateway
  - CloudWatch Logs
  - Secrets Manager
  - IAM

## Project Structure

```
arrms-onspring-integration/
├── src/
│   ├── handlers/              # Lambda function handlers
│   │   ├── onspring_webhook.py
│   │   ├── onspring_to_arrms.py
│   │   └── health_check.py
│   ├── adapters/              # External system clients
│   │   ├── onspring_client.py
│   │   └── arrms_client.py
│   ├── models/                # Data models (to be implemented)
│   ├── utils/                 # Shared utilities
│   │   ├── exceptions.py
│   │   └── response_builder.py
│   └── config/                # Configuration management
│       └── settings.py
├── tests/                     # Unit and integration tests
│   ├── unit/
│   └── integration/
├── events/                    # Sample event payloads
├── docs/                      # Additional documentation
├── template.yaml              # AWS SAM template
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Development dependencies
├── .env.template              # Environment variable template
└── README.md
```

## Setup

### 1. Clone Repository

```bash
git clone https://github.com/Beleza-Asureti/arrms-onspring-integration.git
cd arrms-onspring-integration
```

### 2. Install Dependencies

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.template .env

# Edit .env with your configuration
```

### 4. Set Up AWS Secrets

Store API keys in AWS Secrets Manager:

```bash
# Onspring API Key
aws secretsmanager create-secret \
    --name /arrms-integration/onspring/api-key \
    --secret-string "your-onspring-api-key"

# ARRMS API Key
aws secretsmanager create-secret \
    --name /arrms-integration/arrms/api-key \
    --secret-string "your-arrms-api-key"
```

### 5. Build and Deploy

```bash
# Build the application
sam build

# Deploy to AWS
sam deploy --guided
```

Follow the prompts to configure:
- Stack name (e.g., `arrms-onspring-integration-dev`)
- AWS Region
- Environment (dev/staging/prod)
- Onspring API URL
- ARRMS API URL
- Confirm changes and allow SAM to create IAM roles

## Local Development

### Run Functions Locally

Use AWS SAM CLI to test functions locally:

```bash
# Start API Gateway locally
sam local start-api

# Invoke specific function
sam local invoke OnspringWebhookFunction -e events/onspring-webhook-event.json

# Test with local API endpoint
curl -X POST http://localhost:3000/webhook/onspring \
  -H "Content-Type: application/json" \
  -H "x-api-key: test-key" \
  -d @events/onspring-webhook-event.json
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_onspring_client.py
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
flake8 src/ tests/
pylint src/

# Type checking
mypy src/
```

## API Endpoints

### POST /webhook/onspring

Receives webhook events from Onspring.

**Request:**
```json
{
  "eventType": "RecordCreated",
  "recordId": 12345,
  "appId": 100,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Response:**
```json
{
  "message": "Webhook processed successfully",
  "recordId": 12345,
  "eventType": "RecordCreated"
}
```

### POST /sync/onspring-to-arrms

Triggers synchronization from Onspring to ARRMS.

**Request:**
```json
{
  "app_id": 100,
  "filter": {
    "field": "Status",
    "value": "Active"
  },
  "batch_size": 50
}
```

**Response:**
```json
{
  "message": "Sync completed",
  "summary": {
    "total_records": 150,
    "successful": 148,
    "failed": 2
  },
  "errors": []
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "arrms-onspring-integration",
  "environment": "dev",
  "version": "1.0.0",
  "checks": {
    "environment": "pass"
  }
}
```

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `ENVIRONMENT` | Environment name (dev/staging/prod) | No | `dev` |
| `LOG_LEVEL` | Logging level | No | `INFO` |
| `ONSPRING_API_URL` | Onspring API base URL | No | `https://api.onspring.com/v2` |
| `ONSPRING_API_KEY_SECRET` | Secrets Manager secret name for Onspring API key | Yes | - |
| `ARRMS_API_URL` | ARRMS API base URL | Yes | - |
| `ARRMS_API_KEY_SECRET` | Secrets Manager secret name for ARRMS API key | Yes | - |

### SAM Template Parameters

Configure during deployment:
- `Environment`: dev/staging/prod
- `OnspringApiUrl`: Onspring API endpoint
- `OnspringApiKeySecretName`: Secret Manager path
- `ArrmsApiUrl`: ARRMS API endpoint
- `ArrmsApiKeySecretName`: Secret Manager path
- `LogLevel`: Application log level

## Monitoring and Observability

### CloudWatch Logs

Logs are automatically sent to CloudWatch Logs:
- `/aws/lambda/{stack-name}-onspring-webhook`
- `/aws/lambda/{stack-name}-onspring-to-arrms`
- `/aws/lambda/{stack-name}-health-check`

### Metrics

Custom CloudWatch metrics in namespace `ARRMSIntegration`:
- `WebhookReceived`
- `WebhookProcessed`
- `RecordsRetrieved`
- `RecordsSyncedSuccessfully`
- `RecordsSyncedFailed`

### X-Ray Tracing

AWS X-Ray tracing is enabled for all Lambda functions for distributed tracing.

## Security

### Authentication

- API Gateway uses API Key authentication
- API keys stored in AWS Secrets Manager
- All API requests require `x-api-key` header

### IAM Permissions

Lambda functions have minimal permissions:
- Read secrets from Secrets Manager
- Write logs to CloudWatch
- X-Ray tracing

### Network Security

- HTTPS only for all external API calls
- Retry logic with exponential backoff
- Request timeouts to prevent hanging connections

## Data Transformation

Data transformation logic is implemented in handler functions. Customize the `transform_onspring_to_arrms` and `transform_record` functions to map fields according to your data model.

Example transformation (in `src/handlers/onspring_webhook.py`):

```python
def transform_onspring_to_arrms(onspring_data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform Onspring record to ARRMS format."""
    return {
        "id": onspring_data.get("recordId"),
        "name": onspring_data.get("fields", {}).get("Name"),
        "description": onspring_data.get("fields", {}).get("Description"),
        "status": onspring_data.get("fields", {}).get("Status"),
        "severity": onspring_data.get("fields", {}).get("Severity"),
        "source": "onspring"
    }
```

## Troubleshooting

### Common Issues

**Issue**: Lambda function timing out
- **Solution**: Increase timeout in `template.yaml` (default: 60s)

**Issue**: Cannot retrieve secrets
- **Solution**: Verify IAM role has `secretsmanager:GetSecretValue` permission

**Issue**: API Gateway returns 403
- **Solution**: Verify API key is correct and included in `x-api-key` header

**Issue**: Onspring/ARRMS API errors
- **Solution**: Check CloudWatch Logs for detailed error messages

### Enable Debug Logging

Set `LOG_LEVEL=DEBUG` in environment variables for verbose logging.

## Contributing

1. Create a feature branch
2. Make changes with appropriate tests
3. Ensure code quality checks pass
4. Submit pull request

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/Beleza-Asureti/arrms-onspring-integration/issues
- Documentation: See `/docs` directory

## Roadmap

Future enhancements:
- [ ] Bi-directional sync (ARRMS to Onspring)
- [ ] Field mapping configuration via DynamoDB
- [ ] Enhanced data validation with Pydantic models
- [ ] Batch processing optimization
- [ ] Dead letter queue for failed events
- [ ] CloudFormation nested stacks for multi-environment
- [ ] API versioning support
