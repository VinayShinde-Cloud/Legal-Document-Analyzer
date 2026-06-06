#!/bin/bash
# ============================================================
# Deploy Legal Document Analyzer to AWS
# Uses region from: aws configure get region
# ============================================================

set -e

# Dynamic configuration from aws configure
AWS_REGION=$(aws configure get region)
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
echo "  1. Deploy Bedrock Agents:"
echo "     aws cloudformation create-stack --stack-name AnalyzeDoc-bedrock-agents \\"
echo "       --template-body file://LEGAL-Documents-Collab-Amazon-Model.yaml \\"
echo "       --parameters ParameterKey=EnvironmentName,ParameterValue=LegalDocSetup \\"
echo "         ParameterKey=FoundationModelId,ParameterValue=eu.amazon.nova-pro-v1:0 \\"
echo "       --capabilities CAPABILITY_IAM --region ${AWS_REGION}"
echo ""
echo "  2. Get Agent IDs from stack outputs:"
echo "     aws cloudformation describe-stacks --stack-name AnalyzeDoc-bedrock-agents \\"
echo "       --query 'Stacks[0].Outputs' --region ${AWS_REGION}"
echo ""
echo "  3. Set environment variables and run:"
echo "     export AWS_REGION=${AWS_REGION}"
echo "     export BEDROCK_AGENT_ID=<from-outputs>"
echo "     export BEDROCK_AGENT_ALIAS_ID=<from-outputs>"
echo "     streamlit run Analyze-LegalDocumentsUI.py"
echo ""
