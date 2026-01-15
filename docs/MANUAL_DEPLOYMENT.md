# Manual Command-Line Deployment Guide

This guide provides the exact commands needed to deploy the ARRMS-Onspring Integration Service from the command line using AWS SAM CLI.

## Prerequisites

Before deploying, ensure you have:

1. **AWS CLI** configured with the `dev-asureti` profile
2. **AWS SAM CLI** installed (`pip install aws-sam-cli`)
3. **Python 3.11+** installed
4. **Docker** (optional, only needed for `--use-container` builds)
5. **Valid AWS credentials** with appropriate permissions

## Quick Start

### 1. Build the Application

**Standard Build (No Docker Required)**:
```bash
AWS_PROFILE=dev-asureti sam build --region us-east-1
```

**Container Build (Requires Docker, Recommended for Production)**:
```bash
AWS_PROFILE=dev-asureti sam build --use-container --region us-east-1
```

The container build ensures exact parity with the Lambda runtime environment but requires Docker to be running.

### 2. Deploy to AWS

```bash
AWS_PROFILE=dev-asureti sam deploy \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --s3-prefix arrms-onspring-integration-dev \
  --parameter-overrides \
    Environment=dev \
    OnspringApiUrl=https://api.onspring.com \
    OnspringApiKeySecretName=/arrms-integration/onspring/api-key \
    ArrmsApiUrl=https://api.arrms.placeholder.local \
    ArrmsApiKeySecretName=/arrms-integration/arrms/api-key \
    LogLevel=INFO \
  --tags Environment=dev Project=arrms-onspring-integration ManagedBy=Manual \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset
```

### 3. Verify Deployment

After deployment completes, test the health endpoint:

```bash
API_KEY="qx5Y2ookMbSJfERExOF427sfl2OKnTT74eRlBjc0"
API_URL="https://tfyp2toag2.execute-api.us-east-1.amazonaws.com/dev"

curl -H "x-api-key: ${API_KEY}" ${API_URL}/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "arrms-onspring-integration",
  "environment": "dev",
  "version": "1.0.0"
}
```

## Command Breakdown

### sam build Options

| Flag | Description |
|------|-------------|
| `--region us-east-1` | AWS region for deployment |
| `--use-container` | Build inside Docker container matching Lambda runtime (optional) |

### sam deploy Options

| Flag | Description |
|------|-------------|
| `--stack-name` | CloudFormation stack name |
| `--region` | AWS region for deployment |
| `--capabilities CAPABILITY_IAM` | Allow CloudFormation to create IAM roles |
| `--resolve-s3` | Auto-create/use S3 bucket for deployment artifacts |
| `--s3-prefix` | Prefix for S3 artifacts |
| `--parameter-overrides` | SAM template parameters (see below) |
| `--tags` | CloudFormation stack tags |
| `--no-confirm-changeset` | Skip manual approval prompt |
| `--no-fail-on-empty-changeset` | Don't error if no changes detected |

### Parameter Overrides

| Parameter | Description | Example |
|-----------|-------------|---------|
| `Environment` | Deployment environment | `dev`, `staging`, `prod` |
| `OnspringApiUrl` | Onspring API base URL | `https://api.onspring.com` |
| `OnspringApiKeySecretName` | AWS Secrets Manager secret name | `/arrms-integration/onspring/api-key` |
| `ArrmsApiUrl` | ARRMS API base URL | `https://api.arrms.yourdomain.com` |
| `ArrmsApiKeySecretName` | AWS Secrets Manager secret name | `/arrms-integration/arrms/api-key` |
| `LogLevel` | Lambda function log level | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `OnspringDefaultAppId` | Default Onspring App ID (optional) | `100` |

## Deploying to Different Environments

### Development Environment

```bash
AWS_PROFILE=dev-asureti sam deploy \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --parameter-overrides \
    Environment=dev \
    OnspringApiUrl=https://api.onspring.com \
    OnspringApiKeySecretName=/arrms-integration/dev/onspring/api-key \
    ArrmsApiUrl=https://api.arrms.dev.yourdomain.com \
    ArrmsApiKeySecretName=/arrms-integration/dev/arrms/api-key \
    LogLevel=DEBUG \
  --tags Environment=dev
```

### Production Environment

```bash
AWS_PROFILE=prod-asureti sam deploy \
  --stack-name arrms-onspring-integration-prod \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --parameter-overrides \
    Environment=prod \
    OnspringApiUrl=https://api.onspring.com \
    OnspringApiKeySecretName=/arrms-integration/prod/onspring/api-key \
    ArrmsApiUrl=https://api.arrms.yourdomain.com \
    ArrmsApiKeySecretName=/arrms-integration/prod/arrms/api-key \
    LogLevel=INFO \
  --tags Environment=prod
```

## Updating Configuration

### Change API URLs

To update API URLs without redeploying code:

```bash
AWS_PROFILE=dev-asureti sam deploy \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --parameter-overrides \
    Environment=dev \
    OnspringApiUrl=https://api.onspring.com \
    ArrmsApiUrl=https://api.arrms.NEW-URL.com \
    OnspringApiKeySecretName=/arrms-integration/onspring/api-key \
    ArrmsApiKeySecretName=/arrms-integration/arrms/api-key \
    LogLevel=INFO
```

### Change Log Level

```bash
AWS_PROFILE=dev-asureti sam deploy \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --parameter-overrides \
    Environment=dev \
    OnspringApiUrl=https://api.onspring.com \
    OnspringApiKeySecretName=/arrms-integration/onspring/api-key \
    ArrmsApiUrl=https://api.arrms.placeholder.local \
    ArrmsApiKeySecretName=/arrms-integration/arrms/api-key \
    LogLevel=DEBUG
```

## Updating API Keys in Secrets Manager

After deployment, update the placeholder API keys:

```bash
# Update Onspring API key
aws secretsmanager update-secret \
  --secret-id /arrms-integration/onspring/api-key \
  --secret-string "YOUR_REAL_ONSPRING_API_KEY" \
  --region us-east-1 \
  --profile dev-asureti

# Update ARRMS API key
aws secretsmanager update-secret \
  --secret-id /arrms-integration/arrms/api-key \
  --secret-string "YOUR_REAL_ARRMS_API_KEY" \
  --region us-east-1 \
  --profile dev-asureti
```

## Viewing Deployment Details

### Get Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --profile dev-asureti \
  --query 'Stacks[0].Outputs' \
  --output table
```

### Get API Gateway URL

```bash
aws cloudformation describe-stacks \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --profile dev-asureti \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text
```

### Get Lambda Function ARNs

```bash
aws cloudformation describe-stacks \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --profile dev-asureti \
  --query 'Stacks[0].Outputs[?contains(OutputKey, `FunctionArn`)].{Function:OutputKey,ARN:OutputValue}' \
  --output table
```

## Monitoring and Logs

### Tail Lambda Logs

```bash
# Webhook function
aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-webhook \
  --follow \
  --region us-east-1 \
  --profile dev-asureti

# Sync function
aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-to-arrms \
  --follow \
  --region us-east-1 \
  --profile dev-asureti

# Health check function
aws logs tail /aws/lambda/arrms-onspring-integration-dev-health-check \
  --follow \
  --region us-east-1 \
  --profile dev-asureti
```

### View Recent Logs (Last 10 Minutes)

```bash
aws logs tail /aws/lambda/arrms-onspring-integration-dev-onspring-webhook \
  --since 10m \
  --region us-east-1 \
  --profile dev-asureti
```

## Deleting the Stack

To completely remove all resources:

```bash
AWS_PROFILE=dev-asureti sam delete \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --no-prompts
```

**Warning**: This will delete:
- All Lambda functions
- API Gateway
- CloudWatch Log Groups
- IAM roles
- S3 deployment artifacts

Secrets in AWS Secrets Manager will NOT be deleted automatically.

## Troubleshooting

### Build Fails with Docker Error

If `sam build --use-container` fails:
1. Verify Docker is running: `docker ps`
2. Use standard build instead: `sam build --region us-east-1`

### Deployment Fails with Permission Error

Ensure your AWS profile has the necessary IAM permissions. The deployment role needs:
- CloudFormation (create/update stacks)
- Lambda (create/update functions)
- API Gateway (create/update APIs)
- IAM (create/update roles)
- CloudWatch Logs (create log groups)
- S3 (upload artifacts)
- Secrets Manager (read secrets)

### Stack in ROLLBACK_FAILED State

If a deployment fails and leaves the stack in a bad state:

```bash
# Continue rollback
aws cloudformation continue-update-rollback \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --profile dev-asureti

# Wait for completion
aws cloudformation wait stack-update-complete \
  --stack-name arrms-onspring-integration-dev \
  --region us-east-1 \
  --profile dev-asureti
```

Then retry the deployment.

### Validate Template Before Deployment

```bash
AWS_PROFILE=dev-asureti sam validate --region us-east-1
```

## Best Practices

1. **Always build before deploying** to ensure Lambda packages are up to date
2. **Use `--use-container`** for production deployments to ensure exact runtime match
3. **Test in dev environment first** before deploying to production
4. **Tag your deployments** for better resource tracking
5. **Monitor CloudWatch Logs** after deployment to verify functionality
6. **Keep API keys secure** - never commit them to version control
7. **Use different AWS profiles** for different environments

## Alternative: Guided Deployment

For interactive deployment with prompts:

```bash
AWS_PROFILE=dev-asureti sam deploy --guided
```

This will walk you through all parameters interactively and save your configuration to `samconfig.toml` for future deployments.

## Reference

- AWS SAM CLI Documentation: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference.html
- CloudFormation CLI Reference: https://docs.aws.amazon.com/cli/latest/reference/cloudformation/
- Project README: [../README.md](../README.md)
- Deployment Summary: [../DEPLOYMENT_SUMMARY.md](../DEPLOYMENT_SUMMARY.md)
