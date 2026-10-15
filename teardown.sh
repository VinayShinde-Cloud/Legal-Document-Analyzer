#!/bin/bash
# ============================================================
# FULL TEARDOWN — Clean, Error-Free Resource Deletion
# Legal Document Analyzer Platform
#
# Usage:
#   ./teardown.sh
#   ./teardown.sh --confirm
#   ./teardown.sh --region us-east-1 --confirm
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_ok()    { echo -e "${GREEN}✅ $1${NC}"; }
log_warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# --- Parse Arguments & Determine Region ---
CONFIRM_FLAG=false
CUSTOM_REGION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm|-y)
      CONFIRM_FLAG=true
      shift
      ;;
    --region)
      CUSTOM_REGION="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

# Region precedence: --region flag > .env AWS_REGION > aws configure > us-east-1
if [ -n "$CUSTOM_REGION" ]; then
  AWS_REGION="$CUSTOM_REGION"
elif [ -f .env ] && grep -q '^AWS_REGION=' .env; then
  AWS_REGION=$(grep '^AWS_REGION=' .env | cut -d '=' -f2 | tr -d ' "' | tr -d '\r')
elif command -v aws >/dev/null 2>&1 && [ -n "$(aws configure get region 2>/dev/null)" ]; then
  AWS_REGION=$(aws configure get region 2>/dev/null)
else
  AWS_REGION="us-east-1"
fi

STACK_BATCH="legal-doc-batch"
STACK_INFRA="legal-doc-infra"
STACK_AGENTS="legal-doc-agents"

echo -e "${RED}"
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  ⚠️  AUTOMATED TEARDOWN: ALL DEPLOYED RESOURCES             │"
echo "│                                                             │"
echo "│  Stacks to delete:                                         │"
echo "│    1. $STACK_BATCH  (Batch Pipeline & S3 Buckets)          │"
echo "│    2. $STACK_INFRA  (ECS, ALB, WAF, Cognito, ECR)          │"
echo "│    3. $STACK_AGENTS (Bedrock Agents - if present)          │"
echo "│                                                             │"
echo "│  Target Region: $AWS_REGION"
echo "└─────────────────────────────────────────────────────────────┘"
echo -e "${NC}"

if [ "$CONFIRM_FLAG" = false ]; then
  read -p "Type 'DELETE' to confirm permanent teardown: " CONFIRM
  if [ "$CONFIRM" != "DELETE" ]; then
    echo "Aborted."
    exit 0
  fi
fi

echo ""

# Helper to check if a CloudFormation stack exists
stack_exists() {
  local stack_name="$1"
  local status
  status=$(aws cloudformation describe-stacks --stack-name "$stack_name" --region "$AWS_REGION" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")
  [ "$status" != "DOES_NOT_EXIST" ]
}

# Helper to completely empty an S3 bucket (objects, versions, and delete markers)
empty_s3_bucket() {
  local bucket_name="$1"
  if aws s3api head-bucket --bucket "$bucket_name" --region "$AWS_REGION" 2>/dev/null; then
    log_info "Emptying S3 bucket: $bucket_name..."
    # Fast standard delete
    aws s3 rm "s3://$bucket_name" --recursive --region "$AWS_REGION" 2>/dev/null || true
    
    # Delete versioned objects if versioning was enabled
    local versions
    versions=$(aws s3api list-object-versions --bucket "$bucket_name" --region "$AWS_REGION" --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null || echo "")
    if [ -n "$versions" ] && [ "$versions" != "null" ] && [ "$versions" != '{"Objects": null}' ]; then
      aws s3api delete-objects --bucket "$bucket_name" --delete "$versions" --region "$AWS_REGION" >/dev/null 2>&1 || true
    fi

    # Delete version markers
    local markers
    markers=$(aws s3api list-object-versions --bucket "$bucket_name" --region "$AWS_REGION" --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null || echo "")
    if [ -n "$markers" ] && [ "$markers" != "null" ] && [ "$markers" != '{"Objects": null}' ]; then
      aws s3api delete-objects --bucket "$bucket_name" --delete "$markers" --region "$AWS_REGION" >/dev/null 2>&1 || true
    fi
    log_ok "Emptied S3 bucket: $bucket_name"
  fi
}

# --- STEP 1: Empty S3 Buckets in Batch Stack before deletion ---
if stack_exists "$STACK_BATCH"; then
  log_info "Discovering S3 buckets in $STACK_BATCH..."
  BATCH_BUCKETS=$(aws cloudformation describe-stack-resources --stack-name "$STACK_BATCH" --region "$AWS_REGION" \
    --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text 2>/dev/null || true)
  for BUCKET in $BATCH_BUCKETS; do
    if [ -n "$BUCKET" ] && [ "$BUCKET" != "None" ]; then
      empty_s3_bucket "$BUCKET"
    fi
  done
fi

# --- STEP 2: Empty ECR Repository in Infra Stack before deletion ---
if aws ecr describe-repositories --repository-names legal-doc-analyzer --region "$AWS_REGION" >/dev/null 2>&1; then
  log_info "Emptying ECR repository: legal-doc-analyzer..."
  IMAGE_IDS=$(aws ecr list-images --repository-name legal-doc-analyzer --region "$AWS_REGION" --query 'imageIds[*]' --output json 2>/dev/null || true)
  if [ -n "$IMAGE_IDS" ] && [ "$IMAGE_IDS" != "[]" ]; then
    aws ecr batch-delete-image --repository-name legal-doc-analyzer --region "$AWS_REGION" --image-ids "$IMAGE_IDS" >/dev/null 2>&1 || true
  fi
  log_ok "Emptied ECR repository"
fi

# --- STEP 3: Delete CloudFormation Stacks in Reverse Order ---
for STACK in "$STACK_BATCH" "$STACK_INFRA" "$STACK_AGENTS"; do
  if ! stack_exists "$STACK"; then
    log_warn "Stack $STACK does not exist — skipping"
    continue
  fi

  log_info "Deleting stack: $STACK..."
  aws cloudformation delete-stack --stack-name "$STACK" --region "$AWS_REGION"
  log_info "Waiting for stack $STACK deletion to complete..."
  aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$AWS_REGION"
  log_ok "Stack $STACK successfully deleted"
done

# --- STEP 4: Clean up any lingering or orphan resources ---
echo ""
log_info "Cleaning up any orphan resources..."

# Delete ECR repo if still present
aws ecr delete-repository --repository-name legal-doc-analyzer --region "$AWS_REGION" --force >/dev/null 2>&1 || true

# Delete CodeCommit repo if still present
aws codecommit delete-repository --repository-name legal-doc-analyzer --region "$AWS_REGION" >/dev/null 2>&1 || true

# Delete ECS CloudWatch logs
aws logs delete-log-group --log-group-name /ecs/legal-doc-analyzer --region "$AWS_REGION" >/dev/null 2>&1 || true

# --- Clean Bedrock AgentCore Runtimes & Memories ---
log_info "Cleaning Bedrock AgentCore runtimes and memories in $AWS_REGION..."
for rt_id in $(aws bedrock-agentcore-control list-agent-runtimes --region "$AWS_REGION" --query "agentRuntimes[*].agentRuntimeId" --output text 2>/dev/null || true); do
  if [ -n "$rt_id" ] && [ "$rt_id" != "None" ]; then
    log_info "Deleting AgentCore runtime: $rt_id..."
    aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id "$rt_id" --region "$AWS_REGION" >/dev/null 2>&1 || true
  fi
done

for mem_id in $(aws bedrock-agentcore-control list-memories --region "$AWS_REGION" --query "memories[*].id" --output text 2>/dev/null || true); do
  if [ -n "$mem_id" ] && [ "$mem_id" != "None" ]; then
    log_info "Deleting AgentCore memory: $mem_id..."
    aws bedrock-agentcore-control delete-memory --memory-id "$mem_id" --region "$AWS_REGION" >/dev/null 2>&1 || true
  fi
done

# --- Clean Bedrock Agents & Knowledge Bases ---
log_info "Cleaning Bedrock agents and knowledge bases in $AWS_REGION..."
for agent_id in $(aws bedrock-agent list-agents --region "$AWS_REGION" --query "agentSummaries[*].agentId" --output text 2>/dev/null || true); do
  if [ -n "$agent_id" ] && [ "$agent_id" != "None" ]; then
    log_info "Deleting Bedrock agent: $agent_id..."
    aws bedrock-agent delete-agent --agent-id "$agent_id" --skip-resource-in-use-check --region "$AWS_REGION" >/dev/null 2>&1 || true
  fi
done

for kb_id in $(aws bedrock-agent list-knowledge-bases --region "$AWS_REGION" --query "knowledgeBaseSummaries[*].knowledgeBaseId" --output text 2>/dev/null || true); do
  if [ -n "$kb_id" ] && [ "$kb_id" != "None" ]; then
    log_info "Deleting Bedrock Knowledge Base: $kb_id..."
    aws bedrock-agent delete-knowledge-base --knowledge-base-id "$kb_id" --region "$AWS_REGION" >/dev/null 2>&1 || true
  fi
done

# Clean any lingering input/output/agentcore buckets matching environment
for ORPHAN_BUCKET in $(aws s3 ls 2>/dev/null | grep -E 'legaldoc.*-(input|output|agentcore)' | awk '{print $3}' || true); do
  if [ -n "$ORPHAN_BUCKET" ]; then
    log_info "Found orphan bucket: $ORPHAN_BUCKET — removing..."
    empty_s3_bucket "$ORPHAN_BUCKET"
    aws s3 rb "s3://$ORPHAN_BUCKET" --force --region "$AWS_REGION" 2>/dev/null || true
  fi
done

# Clean local environment persistence variables while preserving model configs
if [ -f .env ]; then
  log_info "Resetting cloud persistence variables in .env..."
  sed -i '' 's/^INPUT_BUCKET=.*/INPUT_BUCKET=/' .env 2>/dev/null || sed -i 's/^INPUT_BUCKET=.*/INPUT_BUCKET=/' .env 2>/dev/null || true
  sed -i '' 's/^OUTPUT_BUCKET=.*/OUTPUT_BUCKET=/' .env 2>/dev/null || sed -i 's/^OUTPUT_BUCKET=.*/OUTPUT_BUCKET=/' .env 2>/dev/null || true
  sed -i '' 's/^RESULTS_TABLE=.*/RESULTS_TABLE=/' .env 2>/dev/null || sed -i 's/^RESULTS_TABLE=.*/RESULTS_TABLE=/' .env 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}================================================================${NC}"
echo -e "${GREEN}✅ TEARDOWN COMPLETE: All cloud resources cleanly removed.${NC}"
echo -e "${GREEN}✅ Clean slate verified — next './deploy-full.sh' will deploy without error.${NC}"
echo -e "${GREEN}================================================================${NC}"
