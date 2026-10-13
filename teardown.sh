#!/bin/bash
# ============================================================
# FULL TEARDOWN — Deletes all deployed resources
# CloudAge Legal Document Analyzer
#
# Usage:
#   ./teardown.sh
#   ./teardown.sh --confirm   (skip confirmation prompt)
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

AWS_REGION=$(aws configure get region 2>/dev/null || echo "eu-north-1")
STACK_AGENTS="legal-doc-agents"
STACK_INFRA="legal-doc-infra"
STACK_BATCH="legal-doc-batch"

echo -e "${RED}"
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  ⚠️  THIS WILL DELETE ALL DEPLOYED RESOURCES               │"
echo "│                                                             │"
echo "│  Stacks to delete:                                         │"
echo "│    • $STACK_BATCH  (Batch Pipeline)"
echo "│    • $STACK_INFRA  (Infrastructure)"
echo "│    • $STACK_AGENTS (Bedrock Agents)"
echo "│                                                             │"
echo "│  Region: $AWS_REGION"
echo "└─────────────────────────────────────────────────────────────┘"
echo -e "${NC}"

if [ "${1:-}" != "--confirm" ]; then
  read -p "Type 'DELETE' to confirm: " CONFIRM
  if [ "$CONFIRM" != "DELETE" ]; then
    echo "Aborted."
    exit 0
  fi
fi

echo ""

# Delete in reverse order
for STACK in "$STACK_BATCH" "$STACK_INFRA" "$STACK_AGENTS"; do
  STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query 'Stacks[0].StackStatus' --output text --region "$AWS_REGION" 2>&1 || true)

  if echo "$STATUS" | grep -q "does not exist"; then
    echo -e "${YELLOW}⏭️  $STACK — does not exist, skipping${NC}"
    continue
  fi

  echo -e "${RED}🗑️  Deleting $STACK...${NC}"
  aws cloudformation delete-stack --stack-name "$STACK" --region "$AWS_REGION"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$AWS_REGION"
  echo -e "${GREEN}✅ $STACK deleted${NC}"
done

# Clean up orphan resources that might remain
echo ""
echo -e "${YELLOW}Cleaning up any orphan resources...${NC}"
aws ecr delete-repository --repository-name legal-doc-analyzer --region "$AWS_REGION" --force 2>/dev/null || true
aws codecommit delete-repository --repository-name legal-doc-analyzer --region "$AWS_REGION" 2>/dev/null || true
aws logs delete-log-group --log-group-name /ecs/legal-doc-analyzer --region "$AWS_REGION" 2>/dev/null || true

# Remove local .env
rm -f .env

echo ""
echo -e "${GREEN}✅ All resources deleted. Clean slate.${NC}"
