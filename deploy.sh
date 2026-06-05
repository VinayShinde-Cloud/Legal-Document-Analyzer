#!/bin/bash
# ============================================================
# Deploy Legal Document Analyzer to AWS
# Prerequisites: AWS CLI configured, Docker installed
# ============================================================

set -e

# Configuration
AWS_REGION="eu-central-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="legal-doc-analyzer"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_URI}/${ECR_REPO}"

echo "============================================"
echo "  CloudAge Legal Document Analyzer - Deploy"
echo "============================================"
echo "Account:  ${ACCOUNT_ID}"
echo "Region:   ${AWS_REGION}"
echo "ECR Repo: ${IMAGE_URI}"
echo ""

# Step 1: Create ECR Repository (if not exists)
echo "📦 Step 1: Creating ECR repository..."
aws ecr describe-repositories --repository-names ${ECR_REPO} --region ${AWS_REGION} 2>/dev/null || \
  aws ecr create-repository --repository-name ${ECR_REPO} --region ${AWS_REGION} --image-scanning-configuration scanOnPush=true

# Step 2: Login to ECR
echo "🔑 Step 2: Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Step 3: Build Docker image
echo "🔨 Step 3: Building Docker image..."
docker build -t ${ECR_REPO}:latest .

# Step 4: Tag and push
echo "🚀 Step 4: Pushing image to ECR..."
docker tag ${ECR_REPO}:latest ${IMAGE_URI}:latest
docker push ${IMAGE_URI}:latest

echo ""
echo "✅ Image pushed successfully: ${IMAGE_URI}:latest"
echo ""
echo "Next steps:"
echo "  1. Create an ECS cluster (if not exists):"
echo "     aws ecs create-cluster --cluster-name legal-doc-analyzer --region ${AWS_REGION}"
echo ""
echo "  2. Create the ECS service with the task definition:"
echo "     aws ecs register-task-definition --cli-input-json file://taskdef.json --region ${AWS_REGION}"
echo "     aws ecs create-service --cluster legal-doc-analyzer --service-name legal-doc-app \\"
echo "       --task-definition legal-doc-analyzer --desired-count 1 --launch-type FARGATE \\"
echo "       --network-configuration 'awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}' \\"
echo "       --region ${AWS_REGION}"
echo ""
echo "  3. Or use AWS Amplify for managed hosting"
echo ""
