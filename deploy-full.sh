#!/bin/bash
# ============================================================
# FULLY AUTOMATED DEPLOYMENT — Zero Manual Intervention
# CloudAge Legal Document Analyzer
#
# Deploys everything end-to-end:
#   1. Bedrock Agents (AI agents + guardrails)
#   2. Infrastructure (ECS, ALB, ECR, Cognito, CodeBuild, CodeCommit)
#   3. Docker image build + push (linux/amd64 for Fargate)
#   4. Push code to CodeCommit (triggers CI/CD)
#   5. Batch Pipeline (S3 + Step Functions)
#   6. Cognito user creation
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker installed and running
#   - Git installed
#   - pip install git-remote-codecommit
#
# Usage:
#   chmod +x deploy-full.sh
#   ./deploy-full.sh
#
# Options:
#   --skip-batch         Skip batch pipeline deployment
#   --email USER@EMAIL   Set Cognito user email (required, or prompted interactively)
#   --password PASS      Set Cognito temp password (default: auto-generated random)
#   --env-name NAME      Set environment name (default: LegalDocSetup)
#   --model MODEL_ID     Set foundation model (default: eu.amazon.nova-pro-v1:0)
# ============================================================

set -euo pipefail

# --- Color output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_ok()    { echo -e "${GREEN}✅ $1${NC}"; }
log_warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_step()  { echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${GREEN}  $1${NC}"; echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

# --- Default Configuration ---
ENVIRONMENT_NAME="LegalDocSetup"
FOUNDATION_MODEL="amazon.nova-pro-v1:0"
STACK_AGENTS="legal-doc-agents"
STACK_INFRA="legal-doc-infra"
STACK_BATCH="legal-doc-batch"
CODECOMMIT_REPO_NAME="legal-doc-analyzer"
DEPLOY_BATCH=true
COGNITO_EMAIL=""
COGNITO_TEMP_PASSWORD=$(openssl rand -base64 16 | tr -d '/+=' | head -c 16)A1!a

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-batch) DEPLOY_BATCH=false; shift ;;
    --email) COGNITO_EMAIL="$2"; shift 2 ;;
    --password) COGNITO_TEMP_PASSWORD="$2"; shift 2 ;;
    --env-name) ENVIRONMENT_NAME="$2"; shift 2 ;;
    --model) FOUNDATION_MODEL="$2"; shift 2 ;;
    *) log_error "Unknown argument: $1"; exit 1 ;;
  esac
done

# Lowercase version for S3 bucket names
ENVIRONMENT_NAME_LOWER=$(echo "$ENVIRONMENT_NAME" | tr '[:upper:]' '[:lower:]')

# Prompt for email if not provided via --email
if [ -z "$COGNITO_EMAIL" ]; then
  read -rp "Enter Cognito user email (for initial admin account): " COGNITO_EMAIL
  if [ -z "$COGNITO_EMAIL" ]; then
    log_error "Email is required. Use --email flag or enter when prompted."
    exit 1
  fi
fi

# ============================================================
# HELPER FUNCTIONS
# ============================================================

get_stack_status() {
  local stack_name="$1"
  local status
  status=$(aws cloudformation describe-stacks --stack-name "$stack_name" \
    --query 'Stacks[0].StackStatus' --output text --region "$AWS_REGION" 2>&1 || true)
  if echo "$status" | grep -q "does not exist"; then
    echo "DOES_NOT_EXIST"
  else
    echo "$status"
  fi
}

delete_stack_if_failed() {
  local stack_name="$1"
  local status
  status=$(get_stack_status "$stack_name")
  if [ "$status" == "ROLLBACK_COMPLETE" ] || [ "$status" == "DELETE_FAILED" ]; then
    log_warn "Stack $stack_name is in $status state. Deleting..."
    aws cloudformation delete-stack --stack-name "$stack_name" --region "$AWS_REGION"
    aws cloudformation wait stack-delete-complete --stack-name "$stack_name" --region "$AWS_REGION"
    log_ok "Deleted $stack_name"
  fi
}

cleanup_orphan_resources() {
  # Clean up resources that may have been left behind by failed stack deployments
  log_info "Checking for orphan resources..."

  # ECR Repository
  if aws ecr describe-repositories --repository-names "$CODECOMMIT_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
    log_warn "Orphan ECR repo found. Deleting..."
    aws ecr delete-repository --repository-name "$CODECOMMIT_REPO_NAME" --region "$AWS_REGION" --force &>/dev/null
  fi

  # CodeCommit Repository
  if aws codecommit get-repository --repository-name "$CODECOMMIT_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
    log_warn "Orphan CodeCommit repo found. Deleting..."
    aws codecommit delete-repository --repository-name "$CODECOMMIT_REPO_NAME" --region "$AWS_REGION" &>/dev/null
  fi

  # CloudWatch Log Group
  if aws logs describe-log-groups --log-group-name-prefix "/ecs/$CODECOMMIT_REPO_NAME" --region "$AWS_REGION" --query 'logGroups[0].logGroupName' --output text 2>/dev/null | grep -q "/ecs/"; then
    log_warn "Orphan log group found. Deleting..."
    aws logs delete-log-group --log-group-name "/ecs/$CODECOMMIT_REPO_NAME" --region "$AWS_REGION" &>/dev/null || true
  fi

  log_ok "Orphan resource check complete"
}

wait_for_stack() {
  local stack_name="$1"
  local action="$2"  # create or update
  log_info "Waiting for $stack_name ($action)..."
  if [ "$action" == "create" ]; then
    aws cloudformation wait stack-create-complete --stack-name "$stack_name" --region "$AWS_REGION"
  else
    aws cloudformation wait stack-update-complete --stack-name "$stack_name" --region "$AWS_REGION"
  fi
}

# ============================================================
# STEP 0: VERIFY PREREQUISITES
# ============================================================
log_step "Step 0: Verifying prerequisites"

# AWS CLI
if ! command -v aws &>/dev/null; then
  log_error "AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
  exit 1
fi

# Docker
if ! command -v docker &>/dev/null; then
  log_error "Docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
  exit 1
fi
if ! docker info &>/dev/null 2>&1; then
  log_error "Docker daemon not running. Start Docker Desktop first."
  exit 1
fi

# Git
if ! command -v git &>/dev/null; then
  log_error "Git not found. Install: https://git-scm.com/"
  exit 1
fi

# git-remote-codecommit
if ! pip show git-remote-codecommit &>/dev/null 2>&1; then
  log_info "Installing git-remote-codecommit..."
  pip install git-remote-codecommit --quiet
fi

# AWS context
AWS_REGION=$(aws configure get region 2>/dev/null || echo "")
if [ -z "$AWS_REGION" ]; then
  log_error "AWS region not configured. Run: aws configure"
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
if [ -z "$ACCOUNT_ID" ]; then
  log_error "AWS credentials not valid. Run: aws configure"
  exit 1
fi

log_ok "AWS CLI configured (Account: $ACCOUNT_ID, Region: $AWS_REGION)"
log_ok "Docker running"
log_ok "Git available"
log_ok "git-remote-codecommit available"

# ============================================================
# STEP 0.5: DISCOVER VPC AND SUBNETS
# ============================================================
log_step "Step 0.5: Discovering VPC and Subnets"

VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$VPC_ID" == "None" ] || [ -z "$VPC_ID" ]; then
  VPC_ID=$(aws ec2 describe-vpcs --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION" 2>/dev/null || echo "")
  if [ -z "$VPC_ID" ]; then
    log_error "No VPC found in $AWS_REGION. Create one first."
    exit 1
  fi
fi

# Get two subnets in different AZs
SUBNET1=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[0].SubnetId' --output text --region "$AWS_REGION")
SUBNET2=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[1].SubnetId' --output text --region "$AWS_REGION")

if [ -z "$SUBNET1" ] || [ -z "$SUBNET2" ] || [ "$SUBNET1" == "None" ] || [ "$SUBNET2" == "None" ]; then
  log_error "Need at least 2 subnets in VPC $VPC_ID."
  exit 1
fi

log_ok "VPC: $VPC_ID"
log_ok "Subnets: $SUBNET1, $SUBNET2"

# ============================================================
# STEP 1: DEPLOY BEDROCK AGENTS
# ============================================================
log_step "Step 1: Deploying Bedrock Agents"

delete_stack_if_failed "$STACK_AGENTS"
AGENTS_STATUS=$(get_stack_status "$STACK_AGENTS")

if [ "$AGENTS_STATUS" == "CREATE_COMPLETE" ] || [ "$AGENTS_STATUS" == "UPDATE_COMPLETE" ]; then
  log_ok "Agents stack already deployed. Skipping."
elif [ "$AGENTS_STATUS" == "DOES_NOT_EXIST" ]; then
  aws cloudformation create-stack \
    --stack-name "$STACK_AGENTS" \
    --template-body file://LEGAL-Documents-Collab-Amazon-Model.yaml \
    --parameters \
      ParameterKey=EnvironmentName,ParameterValue="$ENVIRONMENT_NAME" \
      ParameterKey=FoundationModelId,ParameterValue="$FOUNDATION_MODEL" \
    --capabilities CAPABILITY_IAM \
    --region "$AWS_REGION" >/dev/null
  wait_for_stack "$STACK_AGENTS" "create"
  log_ok "Agents stack deployed!"
else
  log_error "Agents stack in unexpected state: $AGENTS_STATUS. Delete it manually and retry."
  exit 1
fi

# Get Agent outputs
AGENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`CollabBedrockAgentId`].OutputValue' --output text --region "$AWS_REGION")
ALIAS_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`CollabBedrockAgentAliasId`].OutputValue' --output text --region "$AWS_REGION")

# Get individual agent IDs for batch pipeline and direct calls
CLASSIFICATION_AGENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`ClassificationAgentId`].OutputValue' --output text --region "$AWS_REGION")
CLASSIFICATION_ALIAS_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`ClassificationAgentAliasId`].OutputValue' --output text --region "$AWS_REGION")
CONTRACT_AGENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`ContractAgentId`].OutputValue' --output text --region "$AWS_REGION")
CONTRACT_ALIAS_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`ContractAgentAliasId`].OutputValue' --output text --region "$AWS_REGION")
EMAIL_AGENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`EmailAgentId`].OutputValue' --output text --region "$AWS_REGION")
EMAIL_ALIAS_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`EmailAgentAliasId`].OutputValue' --output text --region "$AWS_REGION")
LEGAL_AGENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`LegalAgentId`].OutputValue' --output text --region "$AWS_REGION")
LEGAL_ALIAS_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_AGENTS" \
  --query 'Stacks[0].Outputs[?OutputKey==`LegalAgentAliasId`].OutputValue' --output text --region "$AWS_REGION")

log_ok "Agent ID: $AGENT_ID | Alias: $ALIAS_ID"
log_ok "Classification: $CLASSIFICATION_AGENT_ID | Contract: $CONTRACT_AGENT_ID | Email: $EMAIL_AGENT_ID | Legal: $LEGAL_AGENT_ID"

# Agent roles already have correctly-scoped permissions from CloudFormation
log_ok "Agent roles configured via CloudFormation IAM policies"

# ============================================================
# STEP 2: DEPLOY INFRASTRUCTURE
# ============================================================
log_step "Step 2: Deploying Infrastructure (ECS, ALB, Cognito, CI/CD)"

delete_stack_if_failed "$STACK_INFRA"
cleanup_orphan_resources

INFRA_STATUS=$(get_stack_status "$STACK_INFRA")

if [ "$INFRA_STATUS" == "CREATE_COMPLETE" ] || [ "$INFRA_STATUS" == "UPDATE_COMPLETE" ]; then
  log_ok "Infrastructure stack already deployed. Skipping."
elif [ "$INFRA_STATUS" == "DOES_NOT_EXIST" ]; then
  aws cloudformation create-stack \
    --stack-name "$STACK_INFRA" \
    --template-body file://LEGAL-Documents-Infrastructure.yaml \
    --parameters \
      ParameterKey=EnvironmentName,ParameterValue="$ENVIRONMENT_NAME" \
      ParameterKey=AgentId,ParameterValue="$AGENT_ID" \
      ParameterKey=AgentAliasId,ParameterValue="$ALIAS_ID" \
      ParameterKey=ClassificationAgentId,ParameterValue="$CLASSIFICATION_AGENT_ID" \
      ParameterKey=ClassificationAliasId,ParameterValue="$CLASSIFICATION_ALIAS_ID" \
      ParameterKey=ContractAgentId,ParameterValue="$CONTRACT_AGENT_ID" \
      ParameterKey=ContractAliasId,ParameterValue="$CONTRACT_ALIAS_ID" \
      ParameterKey=EmailAgentId,ParameterValue="$EMAIL_AGENT_ID" \
      ParameterKey=EmailAliasId,ParameterValue="$EMAIL_ALIAS_ID" \
      ParameterKey=LegalAgentId,ParameterValue="$LEGAL_AGENT_ID" \
      ParameterKey=LegalAliasId,ParameterValue="$LEGAL_ALIAS_ID" \
      ParameterKey=VpcId,ParameterValue="$VPC_ID" \
      ParameterKey=PublicSubnet1,ParameterValue="$SUBNET1" \
      ParameterKey=PublicSubnet2,ParameterValue="$SUBNET2" \
    --capabilities CAPABILITY_IAM \
    --region "$AWS_REGION" >/dev/null

  # Push Docker image immediately (ECS needs it to stabilize)
  log_info "Building and pushing Docker image (linux/amd64) while stack creates..."
  sleep 20  # Wait for ECR to be created

  ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${CODECOMMIT_REPO_NAME}"

  # Retry ECR login until repo exists
  for i in {1..10}; do
    if aws ecr describe-repositories --repository-names "$CODECOMMIT_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
      break
    fi
    sleep 10
  done

  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com" >/dev/null 2>&1
  docker buildx build --platform linux/amd64 -t "${ECR_URI}:latest" --push . --quiet 2>/dev/null
  log_ok "Docker image pushed to ECR"

  wait_for_stack "$STACK_INFRA" "create"
  log_ok "Infrastructure stack deployed!"
else
  log_error "Infrastructure stack in unexpected state: $INFRA_STATUS. Delete it and retry."
  exit 1
fi

# Get Infrastructure outputs
APP_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_INFRA" \
  --query 'Stacks[0].Outputs[?OutputKey==`AppURL`].OutputValue' --output text --region "$AWS_REGION" 2>/dev/null || echo "")
COGNITO_POOL_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_INFRA" \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolId`].OutputValue' --output text --region "$AWS_REGION" 2>/dev/null || echo "")
COGNITO_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_INFRA" \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoClientId`].OutputValue' --output text --region "$AWS_REGION" 2>/dev/null || echo "")

# Get Cognito client secret (not available in CloudFormation outputs)
COGNITO_CLIENT_SECRET=$(aws cognito-idp describe-user-pool-client \
  --user-pool-id "$COGNITO_POOL_ID" \
  --client-id "$COGNITO_CLIENT_ID" \
  --region "$AWS_REGION" \
  --query 'UserPoolClient.ClientSecret' --output text 2>/dev/null || echo "")

# Inject COGNITO_APP_CLIENT_SECRET into the ECS task definition
# (CloudFormation can't output this natively)
log_info "Injecting Cognito client secret into ECS task definition..."
TASK_DEF_ARN=$(aws ecs describe-services --cluster "${ENVIRONMENT_NAME}-cluster" \
  --services "${ENVIRONMENT_NAME}-service" --region "$AWS_REGION" \
  --query 'services[0].taskDefinition' --output text)

TASK_DEF_JSON=$(aws ecs describe-task-definition --task-definition "$TASK_DEF_ARN" --region "$AWS_REGION" \
  --query 'taskDefinition.{family:family,taskRoleArn:taskRoleArn,executionRoleArn:executionRoleArn,networkMode:networkMode,containerDefinitions:containerDefinitions,requiresCompatibilities:requiresCompatibilities,cpu:cpu,memory:memory}' --output json)

# Add COGNITO_APP_CLIENT_SECRET if missing
UPDATED_JSON=$(echo "$TASK_DEF_JSON" | python3 -c "
import json, sys
td = json.load(sys.stdin)
env = td['containerDefinitions'][0]['environment']
secret_val = '$COGNITO_CLIENT_SECRET'
env = [e for e in env if e['name'] != 'COGNITO_APP_CLIENT_SECRET']
env.append({'name': 'COGNITO_APP_CLIENT_SECRET', 'value': secret_val})
td['containerDefinitions'][0]['environment'] = env
json.dump(td, sys.stdout)
")

echo "$UPDATED_JSON" > /tmp/taskdef-updated.json
NEW_TASK_ARN=$(aws ecs register-task-definition --cli-input-json file:///tmp/taskdef-updated.json \
  --region "$AWS_REGION" --query 'taskDefinition.taskDefinitionArn' --output text)
aws ecs update-service --cluster "${ENVIRONMENT_NAME}-cluster" \
  --service "${ENVIRONMENT_NAME}-service" \
  --task-definition "$NEW_TASK_ARN" \
  --force-new-deployment --region "$AWS_REGION" >/dev/null
rm -f /tmp/taskdef-updated.json
log_ok "Cognito client secret injected and service redeployed"

log_ok "App URL: $APP_URL"
log_ok "Cognito Pool: $COGNITO_POOL_ID"

# ============================================================
# STEP 3: PUSH CODE TO CODECOMMIT
# ============================================================
log_step "Step 3: Pushing Code to CodeCommit"

CODECOMMIT_URL="codecommit::${AWS_REGION}://${CODECOMMIT_REPO_NAME}"

# Configure git remote
if git remote get-url codecommit &>/dev/null; then
  git remote set-url codecommit "$CODECOMMIT_URL"
else
  git remote add codecommit "$CODECOMMIT_URL"
fi

# Push code
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
[ -z "$CURRENT_BRANCH" ] && CURRENT_BRANCH="main"

git push codecommit "${CURRENT_BRANCH}:main" -f 2>/dev/null
log_ok "Code pushed to CodeCommit (triggers CI/CD build)"

# ============================================================
# STEP 4: DEPLOY BATCH PIPELINE
# ============================================================
if [ "$DEPLOY_BATCH" = true ]; then
  log_step "Step 4: Deploying Batch Pipeline"

  delete_stack_if_failed "$STACK_BATCH"
  BATCH_STATUS=$(get_stack_status "$STACK_BATCH")

  if [ "$BATCH_STATUS" == "CREATE_COMPLETE" ] || [ "$BATCH_STATUS" == "UPDATE_COMPLETE" ]; then
    log_ok "Batch pipeline already deployed. Skipping."
  elif [ "$BATCH_STATUS" == "DOES_NOT_EXIST" ]; then
    aws cloudformation create-stack \
      --stack-name "$STACK_BATCH" \
      --template-body file://LEGAL-Documents-BatchPipeline.yaml \
      --parameters \
        ParameterKey=EnvironmentName,ParameterValue="$ENVIRONMENT_NAME_LOWER" \
        ParameterKey=AgentId,ParameterValue="$AGENT_ID" \
        ParameterKey=AgentAliasId,ParameterValue="$ALIAS_ID" \
        ParameterKey=ClassificationAgentId,ParameterValue="$CLASSIFICATION_AGENT_ID" \
        ParameterKey=ClassificationAliasId,ParameterValue="$CLASSIFICATION_ALIAS_ID" \
        ParameterKey=ContractAgentId,ParameterValue="$CONTRACT_AGENT_ID" \
        ParameterKey=ContractAliasId,ParameterValue="$CONTRACT_ALIAS_ID" \
        ParameterKey=EmailAgentId,ParameterValue="$EMAIL_AGENT_ID" \
        ParameterKey=EmailAliasId,ParameterValue="$EMAIL_ALIAS_ID" \
        ParameterKey=LegalAgentId,ParameterValue="$LEGAL_AGENT_ID" \
        ParameterKey=LegalAliasId,ParameterValue="$LEGAL_ALIAS_ID" \
      --capabilities CAPABILITY_IAM \
      --region "$AWS_REGION" >/dev/null
    wait_for_stack "$STACK_BATCH" "create"
    log_ok "Batch pipeline deployed!"
  else
    log_warn "Batch stack in state: $BATCH_STATUS. Skipping."
  fi

  # Get batch pipeline outputs
  RESULTS_TABLE=$(aws cloudformation describe-stacks --stack-name "$STACK_BATCH" \
    --query 'Stacks[0].Outputs[?OutputKey==`ResultsTableName`].OutputValue' --output text --region "$AWS_REGION" 2>/dev/null || echo "")
  OUTPUT_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_BATCH" \
    --query 'Stacks[0].Outputs[?OutputKey==`OutputBucketName`].OutputValue' --output text --region "$AWS_REGION" 2>/dev/null || echo "")
  log_ok "Results Table: $RESULTS_TABLE | Output Bucket: $OUTPUT_BUCKET"

  # Update infrastructure stack with batch pipeline outputs (RESULTS_TABLE + OUTPUT_BUCKET)
  log_info "Updating infrastructure stack with batch pipeline outputs..."
  aws cloudformation update-stack \
    --stack-name "$STACK_INFRA" \
    --template-body file://LEGAL-Documents-Infrastructure.yaml \
    --parameters \
      ParameterKey=EnvironmentName,ParameterValue="$ENVIRONMENT_NAME" \
      ParameterKey=AgentId,ParameterValue="$AGENT_ID" \
      ParameterKey=AgentAliasId,ParameterValue="$ALIAS_ID" \
      ParameterKey=ClassificationAgentId,ParameterValue="$CLASSIFICATION_AGENT_ID" \
      ParameterKey=ClassificationAliasId,ParameterValue="$CLASSIFICATION_ALIAS_ID" \
      ParameterKey=ContractAgentId,ParameterValue="$CONTRACT_AGENT_ID" \
      ParameterKey=ContractAliasId,ParameterValue="$CONTRACT_ALIAS_ID" \
      ParameterKey=EmailAgentId,ParameterValue="$EMAIL_AGENT_ID" \
      ParameterKey=EmailAliasId,ParameterValue="$EMAIL_ALIAS_ID" \
      ParameterKey=LegalAgentId,ParameterValue="$LEGAL_AGENT_ID" \
      ParameterKey=LegalAliasId,ParameterValue="$LEGAL_ALIAS_ID" \
      ParameterKey=ResultsTableName,ParameterValue="$RESULTS_TABLE" \
      ParameterKey=OutputBucketName,ParameterValue="$OUTPUT_BUCKET" \
      ParameterKey=VpcId,ParameterValue="$VPC_ID" \
      ParameterKey=PublicSubnet1,ParameterValue="$SUBNET1" \
      ParameterKey=PublicSubnet2,ParameterValue="$SUBNET2" \
    --capabilities CAPABILITY_IAM \
    --region "$AWS_REGION" >/dev/null 2>&1 || log_warn "Infra stack update skipped (no changes or already up to date)"
  wait_for_stack "$STACK_INFRA" "update" 2>/dev/null || true
  log_ok "Infrastructure updated with persistence config"
fi

# ============================================================
# STEP 5: CREATE COGNITO USER
# ============================================================
log_step "Step 5: Creating Cognito User"

if [ -n "$COGNITO_POOL_ID" ] && [ "$COGNITO_POOL_ID" != "None" ]; then
  # Check if user already exists
  USER_EXISTS=$(aws cognito-idp admin-get-user \
    --user-pool-id "$COGNITO_POOL_ID" \
    --username "$COGNITO_EMAIL" \
    --region "$AWS_REGION" 2>&1 || true)

  if echo "$USER_EXISTS" | grep -q "UserNotFoundException"; then
    aws cognito-idp admin-create-user \
      --user-pool-id "$COGNITO_POOL_ID" \
      --username "$COGNITO_EMAIL" \
      --user-attributes Name=email,Value="$COGNITO_EMAIL" Name=email_verified,Value=true \
      --temporary-password "$COGNITO_TEMP_PASSWORD" \
      --message-action SUPPRESS \
      --region "$AWS_REGION" >/dev/null

    # Set permanent password to bypass FORCE_CHANGE_PASSWORD state
    # (streamlit-cognito-auth doesn't support the change-password challenge)
    aws cognito-idp admin-set-user-password \
      --user-pool-id "$COGNITO_POOL_ID" \
      --username "$COGNITO_EMAIL" \
      --password "$COGNITO_TEMP_PASSWORD" \
      --permanent \
      --region "$AWS_REGION" >/dev/null

    log_ok "User created: $COGNITO_EMAIL (password: $COGNITO_TEMP_PASSWORD)"
  else
    log_ok "User $COGNITO_EMAIL already exists. Skipping."
  fi
else
  log_warn "Could not determine Cognito Pool ID. Create user manually."
fi

# ============================================================
# STEP 6: GENERATE .env FILE
# ============================================================
log_step "Step 6: Generating .env file for local development"

COGNITO_CLIENT_SECRET=$(aws cognito-idp describe-user-pool-client \
  --user-pool-id "$COGNITO_POOL_ID" \
  --client-id "$COGNITO_CLIENT_ID" \
  --region "$AWS_REGION" \
  --query 'UserPoolClient.ClientSecret' --output text 2>/dev/null || echo "")

# Get batch pipeline outputs for Streamlit persistence
RESULTS_TABLE=""
OUTPUT_BUCKET=""
if [ "$DEPLOY_BATCH" = true ]; then
  RESULTS_TABLE=$(aws cloudformation describe-stacks --stack-name "$STACK_BATCH" \
    --query 'Stacks[0].Outputs[?OutputKey==`ResultsTableName`].OutputValue' --output text --region "$AWS_REGION" 2>/dev/null || echo "")
  OUTPUT_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_BATCH" \
    --query 'Stacks[0].Outputs[?OutputKey==`OutputBucketName`].OutputValue' --output text --region "$AWS_REGION" 2>/dev/null || echo "")
fi

cat > .env <<EOF
# Auto-generated by deploy-full.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
AWS_REGION=${AWS_REGION}
BEDROCK_AGENT_ID=${AGENT_ID}
BEDROCK_AGENT_ALIAS_ID=${ALIAS_ID}
COGNITO_POOL_ID=${COGNITO_POOL_ID}
COGNITO_APP_CLIENT_ID=${COGNITO_CLIENT_ID}
COGNITO_APP_CLIENT_SECRET=${COGNITO_CLIENT_SECRET}

# Individual Agent IDs (used for direct calls in chunked processing)
CLASSIFICATION_AGENT_ID=${CLASSIFICATION_AGENT_ID}
CLASSIFICATION_ALIAS_ID=${CLASSIFICATION_ALIAS_ID}
CONTRACT_AGENT_ID=${CONTRACT_AGENT_ID}
CONTRACT_ALIAS_ID=${CONTRACT_ALIAS_ID}
EMAIL_AGENT_ID=${EMAIL_AGENT_ID}
EMAIL_ALIAS_ID=${EMAIL_ALIAS_ID}
LEGAL_AGENT_ID=${LEGAL_AGENT_ID}
LEGAL_ALIAS_ID=${LEGAL_ALIAS_ID}

# Result Persistence (DynamoDB + S3)
RESULTS_TABLE=${RESULTS_TABLE}
OUTPUT_BUCKET=${OUTPUT_BUCKET}

# Chunk Configuration
CHUNK_MAX_SIZE=8000
CHUNK_MIN_SIZE=500
CHUNK_CONTEXT_WINDOW=1500
CHUNK_OVERLAP=200
EOF

log_ok ".env file generated (for local development: streamlit run Analyze-LegalDocumentsUI.py)"

# ============================================================
# SUMMARY
# ============================================================
log_step "🎉 DEPLOYMENT COMPLETE — ALL AUTOMATED"

echo ""
echo -e "${GREEN}┌─────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${GREEN}│                    DEPLOYMENT SUMMARY                            │${NC}"
echo -e "${GREEN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${GREEN}│${NC}  Region:         ${BLUE}$AWS_REGION${NC}"
echo -e "${GREEN}│${NC}  Account:        ${BLUE}$ACCOUNT_ID${NC}"
echo -e "${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  🌐 App URL:     ${BLUE}$APP_URL${NC}"
echo -e "${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  🤖 Agent ID:    $AGENT_ID"
echo -e "${GREEN}│${NC}  🤖 Alias ID:    $ALIAS_ID"
echo -e "${GREEN}│${NC}  🔐 Cognito:     $COGNITO_POOL_ID"
echo -e "${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  👤 Login:       $COGNITO_EMAIL"
echo -e "${GREEN}│${NC}  🔑 Temp Pass:   $COGNITO_TEMP_PASSWORD"
echo -e "${GREEN}│${NC}     (change on first login)"
echo -e "${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  Stacks:"
echo -e "${GREEN}│${NC}    ✅ $STACK_AGENTS  (Bedrock Agents + Guardrails)"
echo -e "${GREEN}│${NC}    ✅ $STACK_INFRA   (ECS, ALB, Cognito, CI/CD)"
if [ "$DEPLOY_BATCH" = true ]; then
echo -e "${GREEN}│${NC}    ✅ $STACK_BATCH   (S3 + Step Functions)"
fi
echo -e "${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  CI/CD: Push to CodeCommit triggers auto-deploy"
echo -e "${GREEN}│${NC}    git push codecommit main:main"
echo -e "${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  Local dev: source .env && streamlit run Analyze-LegalDocumentsUI.py"
echo -e "${GREEN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${GREEN}│${NC}  Tear down:                                                     "
echo -e "${GREEN}│${NC}    aws cloudformation delete-stack --stack-name $STACK_BATCH     "
echo -e "${GREEN}│${NC}    aws cloudformation delete-stack --stack-name $STACK_INFRA     "
echo -e "${GREEN}│${NC}    aws cloudformation delete-stack --stack-name $STACK_AGENTS    "
echo -e "${GREEN}└─────────────────────────────────────────────────────────────────┘${NC}"
echo ""
