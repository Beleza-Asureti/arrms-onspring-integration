# Deployment Guide

This guide covers deployment of the ARRMS-Onspring Integration Service to AWS using both automated CI/CD pipelines and manual deployment methods.

## Table of Contents

- [Prerequisites](#prerequisites)
- [GitHub Actions CI/CD (Recommended)](#github-actions-cicd-recommended)
- [Manual Deployment](#manual-deployment)
- [Environment Configuration](#environment-configuration)
- [Post-Deployment Setup](#post-deployment-setup)
- [Monitoring and Validation](#monitoring-and-validation)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### AWS Account Setup

1. **AWS Account Access**
   - AWS Account ID: `985444478947`
   - Region: `us-east-1`
   - IAM permissions for SAM deployment

2. **API Credentials**
   - Onspring API key
   - ARRMS API endpoint URL and API key

3. **AWS Secrets Manager**
   ```bash
   # Create secrets if they don't exist
   aws secretsmanager create-secret \
       --name /arrms-integration/onspring/api-key \
       --secret-string "YOUR_ONSPRING_API_KEY" \
       --region us-east-1

   aws secretsmanager create-secret \
       --name /arrms-integration/arrms/api-key \
       --secret-string "YOUR_ARRMS_API_KEY" \
       --region us-east-1
   ```

### Development Tools

- Python 3.11+
- AWS CLI v2
- AWS SAM CLI
- Docker (for SAM local testing)

## GitHub Actions CI/CD (Recommended)

### Overview

The repository is configured with GitHub Actions for automated deployment using OIDC authentication (no long-lived credentials).

### IAM Configuration

**IAM Role**: `github-actions-arrms-integration`
**ARN**: `arn:aws:iam::985444478947:role/github-actions-arrms-integration`
**Policy**: `github-actions-arrms-integration-policy`

This role has permissions for:
- CloudFormation stack management
- Lambda function deployment
- API Gateway configuration
- IAM role creation for Lambda execution
- CloudWatch Logs management
- S3 bucket access for SAM artifacts
- Secrets Manager read access

### GitHub Repository Secrets

Configure these secrets in your GitHub repository:

1. Navigate to: `Settings > Secrets and variables > Actions`
2. Add the following secrets:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `ONSPRING_API_URL` | Onspring API base URL | `https://api.onspring.com/v2` |
| `ARRMS_API_URL` | ARRMS API base URL | `https://api.arrms.example.com` |

**Note**: API keys are stored in AWS Secrets Manager, not GitHub Secrets.

### Workflow Configuration

The deployment workflow (`.github/workflows/deploy.yml`) runs on:

- **Push to main**: Automatically deploys to `dev` environment
- **Pull request**: Runs tests and validation only
- **Manual trigger**: Allows deployment to any environment via workflow_dispatch

### Workflow Steps

1. **Lint and Test**
   - Python code linting with flake8
   - Code formatting check with black
   - Unit tests with pytest and coverage

2. **Validate**
   - SAM template validation
   - Template linting

3. **Deploy to Dev**
   - Configure AWS credentials via OIDC
   - Build Lambda functions with SAM
   - Deploy CloudFormation stack
   - Run smoke tests
   - Output API endpoint URL

### Manual Workflow Trigger

To manually trigger a deployment:

1. Go to: `Actions > Deploy to AWS > Run workflow`
2. Select branch (usually `main`)
3. Choose environment (`dev`, `staging`, or `prod`)
4. Click "Run workflow"

## Manual Deployment

### Using SAM CLI

#### 1. Set Up Environment

```bash
# Clone repository
git clone https://github.com/Beleza-Asureti/arrms-onspring-integration.git
cd arrms-onspring-integration

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
```

#### 2. Configure AWS Credentials

```bash
# Option 1: AWS SSO
aws sso login --profile dev-asureti

# Option 2: Export credentials
export AWS_PROFILE=dev-asureti
export AWS_REGION=us-east-1
```

#### 3. Build Application

```bash
# Build with SAM
sam build

# Optional: Build with container (matches Lambda runtime exactly)
sam build --use-container
```

#### 4. Deploy

```bash
# Interactive deployment (first time)
sam deploy --guided --profile dev-asureti

# Non-interactive deployment (uses samconfig.toml)
sam deploy --profile dev-asureti

# Deploy to specific environment
sam deploy --config-env dev --profile dev-asureti
sam deploy --config-env staging --profile dev-asureti
sam deploy --config-env prod --profile dev-asureti
```

#### 5. Deployment Parameters

During `sam deploy --guided`, you'll be prompted for:

- **Stack Name**: `arrms-onspring-integration-dev`
- **AWS Region**: `us-east-1`
- **Parameter Environment**: `dev`
- **Parameter OnspringApiUrl**: `https://api.onspring.com/v2`
- **Parameter OnspringApiKeySecretName**: `/arrms-integration/onspring/api-key`
- **Parameter ArrmsApiUrl**: Your ARRMS API URL
- **Parameter ArrmsApiKeySecretName**: `/arrms-integration/arrms/api-key`
- **Parameter LogLevel**: `INFO`
- **Confirm changes**: `Y`
- **Allow SAM CLI IAM role creation**: `Y`
- **Save arguments to samconfig.toml**: `Y`

## Environment Configuration

### Development (dev)

- **Stack Name**: `arrms-onspring-integration-dev`
- **Log Level**: `DEBUG`
- **Purpose**: Development and testing
- **Monitoring**: Basic CloudWatch monitoring

### Staging (staging)

- **Stack Name**: `arrms-onspring-integration-staging`
- **Log Level**: `INFO`
- **Purpose**: Pre-production validation
- **Monitoring**: Enhanced monitoring

### Production (prod)

- **Stack Name**: `arrms-onspring-integration-prod`
- **Log Level**: `WARNING`
- **Purpose**: Production workloads
- **Monitoring**: Full monitoring with alarms

## Post-Deployment Setup

### 1. Retrieve API Information

```bash
# Get API Gateway URL
aws cloudformation describe-stacks \
  --stack-name arrms-onspring-integration-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text

# Get API Gateway ID
aws cloudformation describe-stacks \
  --stack-name arrms-onspring-integration-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiId`].OutputValue' \
  --output text
```

### 2. Get API Key

```bash
# List API keys
aws apigateway get-api-keys --include-values --region us-east-1

# Or get specific key
API_ID=$(aws cloudformation describe-stacks \
  --stack-name arrms-onspring-integration-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiId`].OutputValue' \
  --output text)

aws apigateway get-api-keys \
  --query "items[?name=='arrms-onspring-integration-dev-api-key'].{Name:name,Value:value}" \
  --include-values \
  --region us-east-1
```

### 3. Configure Onspring Webhook

1. Log in to Onspring
2. Navigate to webhook configuration
3. Add webhook URL: `https://<api-url>/dev/webhook/onspring`
4. Set method: `POST`
5. Add header: `x-api-key: <your-api-key>`
6. Select events to trigger webhook

### 4. Test Deployment

```bash
# Health check
curl -H "x-api-key: YOUR_API_KEY" \
  https://YOUR_API_URL/dev/health

# Test webhook (local)
sam local invoke OnspringWebhookFunction \
  -e events/onspring-webhook-event.json

# Test sync (local)
sam local invoke OnspringToArrmsFunction \
  -e events/sync-request-event.json
```

## Monitoring and Validation

### CloudWatch Logs

Access logs for each function:

```bash
# Webhook function logs
aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-webhook --follow

# Sync function logs
aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-to-arrms --follow

# Health check logs
aws logs tail /aws/lambda/arrms-onspring-integration-dev-health-check --follow
```

### CloudWatch Metrics

View custom metrics in CloudWatch Console:

- Namespace: `ARRMSIntegration`
- Metrics:
  - `WebhookReceived`
  - `WebhookProcessed`
  - `RecordsRetrieved`
  - `RecordsSyncedSuccessfully`
  - `RecordsSyncedFailed`

### X-Ray Tracing

View distributed traces in AWS X-Ray Console:

1. Navigate to: AWS X-Ray > Service Map
2. Select time range
3. View request traces and performance

### Smoke Tests

Run smoke tests after deployment:

```bash
# Set variables
API_URL="https://YOUR_API_URL/dev"
API_KEY="YOUR_API_KEY"

# Health check
curl -f -H "x-api-key: $API_KEY" "$API_URL/health"

# Expected response
# {"status":"healthy","service":"arrms-onspring-integration",...}
```

## Troubleshooting

### Common Issues

#### 1. Deployment Fails - Insufficient Permissions

**Error**: `User is not authorized to perform: cloudformation:CreateStack`

**Solution**: Ensure IAM role has correct permissions. For GitHub Actions, verify:
- Role ARN is correct in workflow
- Trust policy allows your repository
- Policy includes all required permissions

#### 2. Lambda Function Timeout

**Error**: `Task timed out after 60.00 seconds`

**Solution**: Increase timeout in `template.yaml`:
```yaml
Timeout: 300  # 5 minutes
```

#### 3. Cannot Access Secrets

**Error**: `Error retrieving secret: AccessDeniedException`

**Solution**: Verify:
- Secret exists in Secrets Manager
- Secret name matches parameter
- Lambda execution role has `secretsmanager:GetSecretValue` permission
- Secret is in same region as Lambda

#### 4. API Gateway 403 Forbidden

**Error**: `{"message":"Forbidden"}`

**Solution**: Verify:
- API key is included in request header `x-api-key`
- API key is valid and not expired
- API key is associated with usage plan

#### 5. GitHub Actions OIDC Authentication Fails

**Error**: `Error: Not authorized to perform sts:AssumeRoleWithWebIdentity`

**Solution**: Verify:
- Trust policy includes correct repository name
- OIDC provider exists in AWS account
- Token audience is `sts.amazonaws.com`

### Debug Mode

Enable debug logging:

```bash
# Update stack with DEBUG log level
sam deploy --parameter-overrides LogLevel=DEBUG

# Or update via CloudFormation
aws cloudformation update-stack \
  --stack-name arrms-onspring-integration-dev \
  --use-previous-template \
  --parameters ParameterKey=LogLevel,ParameterValue=DEBUG \
  --capabilities CAPABILITY_IAM
```

### Stack Deletion

To completely remove the deployment:

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack \
  --stack-name arrms-onspring-integration-dev

# Wait for deletion
aws cloudformation wait stack-delete-complete \
  --stack-name arrms-onspring-integration-dev

# Clean up S3 artifacts bucket (if needed)
aws s3 rb s3://aws-sam-cli-managed-default-XXXXX --force
```

## Best Practices

### 1. Environment Isolation

- Use separate stacks for dev/staging/prod
- Use separate secrets for each environment
- Tag all resources with environment

### 2. Security

- Rotate API keys regularly
- Use least-privilege IAM policies
- Enable CloudTrail logging
- Review CloudWatch Logs for anomalies

### 3. Cost Optimization

- Set appropriate Lambda memory sizes
- Use CloudWatch Log retention policies
- Monitor Lambda invocations and duration
- Clean up old CloudFormation stacks

### 4. Deployment Strategy

- Always test in dev first
- Use canary or blue/green deployments for prod
- Tag deployments with commit SHA
- Maintain rollback capability

## Additional Resources

- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [GitHub Actions OIDC Guide](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [Lambda Powertools Documentation](https://awslabs.github.io/aws-lambda-powertools-python/)
- [API Gateway Documentation](https://docs.aws.amazon.com/apigateway/)

## Support

For deployment issues:
1. Check CloudWatch Logs for error details
2. Review GitHub Actions workflow runs
3. Consult troubleshooting section above
4. Open GitHub issue with deployment logs
