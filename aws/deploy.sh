#!/usr/bin/env bash
# =============================================================================
# VEL Trading Platform - AWS Full Automated Deployment Orchestrator
# =============================================================================
# This script provides complete automated deployment including:
# - Infrastructure provisioning (EKS, RDS, ElastiCache, S3)
# - GitHub to AWS CI/CD pipeline (CodePipeline + CodeBuild + CodeDeploy)
# - Application deployment with Helm
# - Monitoring and logging setup
# - SSL/TLS certificate management
# - Auto-scaling configuration
# =============================================================================
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
readonly LOG_FILE="${SCRIPT_DIR}/deploy_${TIMESTAMP}.log"

# VEL-specific configuration
export VEL_REGION="${VEL_REGION:-us-east-1}"
export VEL_EKS_NAME="${VEL_EKS_NAME:-vel-prod}"
export VEL_DNS_ZONE="${VEL_DNS_ZONE:-kessann.bot}"
export VEL_ENVIRONMENT="${VEL_ENVIRONMENT:-production}"
export VEL_GITHUB_REPO="${VEL_GITHUB_REPO:-}"
export VEL_GITHUB_BRANCH="${VEL_GITHUB_BRANCH:-main}"
export VEL_ECR_REPO="${VEL_ECR_REPO:-vel-trading}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================
vel_log() {
    local level="$1"
    local message="$2"
    local timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "${timestamp} [${level}] ${message}" | tee -a "${LOG_FILE}"
}

vel_info() { vel_log "${BLUE}INFO${NC}" "$1"; }
vel_success() { vel_log "${GREEN}SUCCESS${NC}" "$1"; }
vel_warning() { vel_log "${YELLOW}WARNING${NC}" "$1"; }
vel_error() { vel_log "${RED}ERROR${NC}" "$1"; }
vel_step() { echo -e "\n${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; vel_log "${CYAN}STEP${NC}" "$1"; }

# =============================================================================
# PREREQUISITE CHECKS
# =============================================================================
vel_check_prerequisites() {
    vel_step "Checking deployment prerequisites..."
    
    local required_tools=("aws" "terraform" "helm" "kubectl" "docker" "git")
    local missing_tools=()
    
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_tools+=("$tool")
        else
            vel_info "✓ Found: $tool"
        fi
    done
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        vel_error "Missing required tools: ${missing_tools[*]}"
        vel_info "Install missing tools and re-run"
        exit 1
    fi
    
    vel_success "All prerequisites satisfied"
}

# =============================================================================
# AWS AUTHENTICATION
# =============================================================================
vel_verify_aws_auth() {
    vel_step "Authenticating with AWS..."
    
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        vel_error "Invalid AWS credentials. Configure with 'aws configure'"
        exit 1
    fi
    
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    local caller_arn=$(aws sts get-caller-identity --query Arn --output text)
    
    vel_info "AWS Account: ${account_id}"
    vel_info "Caller ARN: ${caller_arn}"
    vel_success "AWS authentication successful"
}

# =============================================================================
# ECR REPOSITORY SETUP
# =============================================================================
vel_setup_ecr() {
    vel_step "Setting up ECR repository..."
    
    local ecr_uri="${AWS_ACCOUNT_ID}.dkr.ecr.${VEL_REGION}.amazonaws.com/${VEL_ECR_REPO}"
    
    # Create ECR repository if it doesn't exist
    if ! aws ecr describe-repositories --repository-names "${VEL_ECR_REPO}" --region "${VEL_REGION}" >/dev/null 2>&1; then
        vel_info "Creating ECR repository: ${VEL_ECR_REPO}"
        aws ecr create-repository \
            --repository-name "${VEL_ECR_REPO}" \
            --region "${VEL_REGION}" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256
        vel_success "ECR repository created"
    else
        vel_info "ECR repository already exists"
    fi
    
    # Login to ECR
    vel_info "Logging into ECR..."
    aws ecr get-login-password --region "${VEL_REGION}" | docker login --username AWS --password-stdin "${ecr_uri%/*}"
    
    vel_success "ECR setup complete"
    echo "${ecr_uri}"
}

# =============================================================================
# GITHUB CI/CD INTEGRATION (CodePipeline + CodeBuild)
# =============================================================================
vel_setup_github_cicd() {
    vel_step "Setting up GitHub to AWS CI/CD Pipeline (CodePipeline)..."
    
    if [ -z "${VEL_GITHUB_REPO}" ]; then
        vel_warning "VEL_GITHUB_REPO not set. Skipping CI/CD setup."
        vel_info "Set VEL_GITHUB_REPO=owner/repo to enable GitHub integration"
        return
    fi
    
    local pipeline_name="vel-${VEL_ENVIRONMENT}-pipeline"
    local codebuild_project="vel-${VEL_ENVIRONMENT}-build"
    
    vel_info "Creating IAM roles for CodePipeline..."
    
    # Create CodePipeline service role
    cat > /tmp/codepipeline-trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "codepipeline.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

    # Create CodeBuild service role
    cat > /tmp/codebuild-trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "codebuild.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

    # Create roles if they don't exist
    if ! aws iam get-role --role-name vel-codepipeline-role >/dev/null 2>&1; then
        aws iam create-role \
            --role-name vel-codepipeline-role \
            --assume-role-policy-document file:///tmp/codepipeline-trust-policy.json
        
        aws iam attach-role-policy \
            --role-name vel-codepipeline-role \
            --policy-arn arn:aws:iam::aws:policy/AWSCodePipeline_FullAccess
        
        aws iam attach-role-policy \
            --role-name vel-codepipeline-role \
            --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
        
        aws iam attach-role-policy \
            --role-name vel-codepipeline-role \
            --policy-arn arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess
        
        vel_info "Created CodePipeline role"
    fi
    
    if ! aws iam get-role --role-name vel-codebuild-role >/dev/null 2>&1; then
        aws iam create-role \
            --role-name vel-codebuild-role \
            --assume-role-policy-document file:///tmp/codebuild-trust-policy.json
        
        aws iam attach-role-policy \
            --role-name vel-codebuild-role \
            --policy-arn arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess
        
        aws iam attach-role-policy \
            --role-name vel-codebuild-role \
            --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
        
        aws iam attach-role-policy \
            --role-name vel-codebuild-role \
            --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
        
        aws iam attach-role-policy \
            --role-name vel-codebuild-role \
            --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess
        
        vel_info "Created CodeBuild role"
    fi
    
    # Wait for IAM propagation
    sleep 10
    
    vel_info "Creating CodeBuild project..."
    
    # Create buildspec if it doesn't exist
    if [ ! -f "${SCRIPT_DIR}/../buildspec.yml" ]; then
        vel_create_buildspec
    fi
    
    # Create CodeBuild project
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    
    cat > /tmp/codebuild-project.json << EOF
{
    "name": "${codebuild_project}",
    "description": "VEL Trading Platform Build Project",
    "source": {
        "type": "CODEPIPELINE",
        "buildspec": "buildspec.yml"
    },
    "artifacts": {
        "type": "CODEPIPELINE"
    },
    "environment": {
        "type": "LINUX_CONTAINER",
        "image": "aws/codebuild/amazonlinux2-x86_64-standard:4.0",
        "computeType": "BUILD_GENERAL1_MEDIUM",
        "privilegedMode": true,
        "environmentVariables": [
            {"name": "AWS_DEFAULT_REGION", "value": "${VEL_REGION}"},
            {"name": "AWS_ACCOUNT_ID", "value": "${account_id}"},
            {"name": "IMAGE_REPO_NAME", "value": "${VEL_ECR_REPO}"},
            {"name": "IMAGE_TAG", "value": "latest"},
            {"name": "EKS_CLUSTER_NAME", "value": "${VEL_EKS_NAME}"}
        ]
    },
    "serviceRole": "arn:aws:iam::${account_id}:role/vel-codebuild-role",
    "timeoutInMinutes": 30,
    "logsConfig": {
        "cloudWatchLogs": {
            "status": "ENABLED",
            "groupName": "/aws/codebuild/${codebuild_project}"
        }
    }
}
EOF

    if ! aws codebuild batch-get-projects --names "${codebuild_project}" --query 'projects[0].name' --output text 2>/dev/null | grep -q "${codebuild_project}"; then
        aws codebuild create-project --cli-input-json file:///tmp/codebuild-project.json
        vel_info "CodeBuild project created"
    else
        vel_info "CodeBuild project already exists"
    fi
    
    vel_info "Creating S3 bucket for artifacts..."
    local artifact_bucket="vel-pipeline-artifacts-${account_id}-${VEL_REGION}"
    
    if ! aws s3api head-bucket --bucket "${artifact_bucket}" 2>/dev/null; then
        aws s3api create-bucket \
            --bucket "${artifact_bucket}" \
            --region "${VEL_REGION}" \
            $([ "${VEL_REGION}" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=${VEL_REGION}")
        vel_info "Artifact bucket created"
    fi
    
    vel_info "Setting up GitHub connection..."
    vel_info "NOTE: You need to complete GitHub connection in AWS Console:"
    vel_info "1. Go to AWS Console > Developer Tools > Settings > Connections"
    vel_info "2. Create a connection to GitHub"
    vel_info "3. Authorize AWS to access your repository"
    
    # Check for existing connection
    local connection_arn=$(aws codestar-connections list-connections --provider-type GitHub --query "Connections[?ConnectionStatus=='AVAILABLE'].ConnectionArn" --output text 2>/dev/null | head -1)
    
    if [ -n "${connection_arn}" ]; then
        vel_info "Found existing GitHub connection: ${connection_arn}"
        
        vel_info "Creating CodePipeline..."
        
        cat > /tmp/codepipeline.json << EOF
{
    "pipeline": {
        "name": "${pipeline_name}",
        "roleArn": "arn:aws:iam::${account_id}:role/vel-codepipeline-role",
        "artifactStore": {
            "type": "S3",
            "location": "${artifact_bucket}"
        },
        "stages": [
            {
                "name": "Source",
                "actions": [
                    {
                        "name": "GitHub_Source",
                        "actionTypeId": {
                            "category": "Source",
                            "owner": "AWS",
                            "provider": "CodeStarSourceConnection",
                            "version": "1"
                        },
                        "configuration": {
                            "ConnectionArn": "${connection_arn}",
                            "FullRepositoryId": "${VEL_GITHUB_REPO}",
                            "BranchName": "${VEL_GITHUB_BRANCH}",
                            "OutputArtifactFormat": "CODE_ZIP"
                        },
                        "outputArtifacts": [{"name": "SourceOutput"}],
                        "runOrder": 1
                    }
                ]
            },
            {
                "name": "Build",
                "actions": [
                    {
                        "name": "Build",
                        "actionTypeId": {
                            "category": "Build",
                            "owner": "AWS",
                            "provider": "CodeBuild",
                            "version": "1"
                        },
                        "configuration": {
                            "ProjectName": "${codebuild_project}"
                        },
                        "inputArtifacts": [{"name": "SourceOutput"}],
                        "outputArtifacts": [{"name": "BuildOutput"}],
                        "runOrder": 1
                    }
                ]
            },
            {
                "name": "Deploy",
                "actions": [
                    {
                        "name": "Deploy_to_EKS",
                        "actionTypeId": {
                            "category": "Build",
                            "owner": "AWS",
                            "provider": "CodeBuild",
                            "version": "1"
                        },
                        "configuration": {
                            "ProjectName": "${codebuild_project}",
                            "EnvironmentVariables": "[{\\"name\\":\\"DEPLOY_PHASE\\",\\"value\\":\\"true\\",\\"type\\":\\"PLAINTEXT\\"}]"
                        },
                        "inputArtifacts": [{"name": "BuildOutput"}],
                        "runOrder": 1
                    }
                ]
            }
        ]
    }
}
EOF
        
        if ! aws codepipeline get-pipeline --name "${pipeline_name}" >/dev/null 2>&1; then
            aws codepipeline create-pipeline --cli-input-json file:///tmp/codepipeline.json
            vel_success "CodePipeline created: ${pipeline_name}"
        else
            vel_info "Pipeline already exists, updating..."
            aws codepipeline update-pipeline --cli-input-json file:///tmp/codepipeline.json
            vel_success "CodePipeline updated"
        fi
    else
        vel_warning "No GitHub connection found. Please create one in AWS Console."
        vel_info "After creating connection, re-run this script."
    fi
    
    vel_success "GitHub CI/CD setup complete"
}

# =============================================================================
# CREATE BUILDSPEC FILE
# =============================================================================
vel_create_buildspec() {
    vel_info "Creating buildspec.yml for CodeBuild..."
    
    cat > "${SCRIPT_DIR}/../buildspec.yml" << 'EOF'
version: 0.2

env:
  variables:
    DOCKER_BUILDKIT: "1"

phases:
  pre_build:
    commands:
      - echo "Logging in to Amazon ECR..."
      - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
      - REPOSITORY_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$IMAGE_REPO_NAME
      - COMMIT_HASH=$(echo $CODEBUILD_RESOLVED_SOURCE_VERSION | cut -c 1-7)
      - IMAGE_TAG=${COMMIT_HASH:=latest}
      - echo "Installing dependencies..."
      - pip install -r requirements.txt || true

  build:
    commands:
      - echo "Build started on `date`"
      - echo "Building Docker image..."
      - |
        if [ -f Dockerfile ]; then
          docker build -t $REPOSITORY_URI:latest .
          docker tag $REPOSITORY_URI:latest $REPOSITORY_URI:$IMAGE_TAG
        else
          echo "No Dockerfile found, creating one..."
          cat > Dockerfile << 'DOCKERFILE'
        FROM python:3.11-slim
        WORKDIR /app
        COPY requirements.txt .
        RUN pip install --no-cache-dir -r requirements.txt
        COPY . .
        ENV PYTHONUNBUFFERED=1
        EXPOSE 5000
        CMD ["python", "anvel_web_server.py"]
        DOCKERFILE
          docker build -t $REPOSITORY_URI:latest .
          docker tag $REPOSITORY_URI:latest $REPOSITORY_URI:$IMAGE_TAG
        fi

  post_build:
    commands:
      - echo "Build completed on `date`"
      - echo "Pushing Docker image to ECR..."
      - docker push $REPOSITORY_URI:latest
      - docker push $REPOSITORY_URI:$IMAGE_TAG
      - |
        if [ "$DEPLOY_PHASE" = "true" ]; then
          echo "Deploying to EKS..."
          aws eks update-kubeconfig --region $AWS_DEFAULT_REGION --name $EKS_CLUSTER_NAME
          kubectl set image deployment/vel-trading vel-trading=$REPOSITORY_URI:$IMAGE_TAG -n vel-system || \
          helm upgrade --install vel-trading ./aws/helm/vel \
            --namespace vel-system \
            --create-namespace \
            --set image.repository=$REPOSITORY_URI \
            --set image.tag=$IMAGE_TAG \
            --wait --timeout 10m
        fi
      - printf '[{"name":"vel-trading","imageUri":"%s"}]' $REPOSITORY_URI:$IMAGE_TAG > imagedefinitions.json

artifacts:
  files:
    - imagedefinitions.json
    - '**/*'

cache:
  paths:
    - '/root/.cache/pip/**/*'
    - '/root/.docker/**/*'
EOF

    vel_success "buildspec.yml created"
}

# =============================================================================
# INFRASTRUCTURE PROVISIONING
# =============================================================================
vel_provision_infrastructure() {
    vel_step "Provisioning VEL cloud infrastructure..."
    
    cd "${SCRIPT_DIR}/terraform"
    
    vel_info "Initializing Terraform..."
    terraform init -input=false -upgrade
    
    vel_info "Planning infrastructure changes..."
    terraform plan -out="vel_plan_${TIMESTAMP}.tfplan" \
        -var="region=${VEL_REGION}" \
        -var="cluster_name=${VEL_EKS_NAME}" \
        -var="environment=${VEL_ENVIRONMENT}"
    
    vel_info "Applying infrastructure changes..."
    terraform apply -auto-approve "vel_plan_${TIMESTAMP}.tfplan"
    
    rm -f "vel_plan_${TIMESTAMP}.tfplan"
    
    vel_success "Infrastructure provisioned successfully"
}

# =============================================================================
# KUBERNETES CONFIGURATION
# =============================================================================
vel_configure_kubernetes() {
    vel_step "Configuring Kubernetes access..."
    
    aws eks update-kubeconfig \
        --region "${VEL_REGION}" \
        --name "${VEL_EKS_NAME}" \
        --alias "vel-cluster"
    
    vel_info "Verifying cluster access..."
    kubectl cluster-info
    
    vel_success "Kubernetes configured"
}

# =============================================================================
# MONITORING SETUP
# =============================================================================
vel_install_monitoring() {
    vel_step "Setting up cluster monitoring..."
    
    vel_info "Installing metrics server..."
    kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml || true
    
    vel_info "Installing Prometheus (if Helm chart available)..."
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
    helm repo update || true
    
    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        --namespace monitoring \
        --create-namespace \
        --set grafana.enabled=true \
        --set alertmanager.enabled=true \
        --wait --timeout 10m || vel_warning "Prometheus installation skipped"
    
    vel_success "Monitoring setup complete"
}

# =============================================================================
# APPLICATION DEPLOYMENT
# =============================================================================
vel_deploy_application() {
    vel_step "Deploying VEL trading application..."
    
    # Build frontend if it exists
    if [ -d "${SCRIPT_DIR}/../frontend" ]; then
        vel_info "Building frontend..."
        cd "${SCRIPT_DIR}/../frontend"
        npm install
        npm run build
        cd "${SCRIPT_DIR}"
    fi
    
    vel_info "Deploying with Helm..."
    helm upgrade --install vel-trading "${SCRIPT_DIR}/helm/vel" \
        --namespace vel-system \
        --create-namespace \
        --set global.domain="${VEL_DNS_ZONE}" \
        --set global.environment="${VEL_ENVIRONMENT}" \
        --set image.tag="latest" \
        --wait \
        --timeout 10m
    
    vel_success "Application deployed"
}

# =============================================================================
# SSL/TLS SETUP
# =============================================================================
vel_setup_ssl() {
    vel_step "Setting up SSL/TLS certificates..."
    
    vel_info "Installing cert-manager..."
    helm repo add jetstack https://charts.jetstack.io || true
    helm repo update || true
    
    kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.crds.yaml || true
    
    helm upgrade --install cert-manager jetstack/cert-manager \
        --namespace cert-manager \
        --create-namespace \
        --set installCRDs=false \
        --wait --timeout 5m || vel_warning "cert-manager installation skipped"
    
    vel_success "SSL/TLS setup complete"
}

# =============================================================================
# DEPLOYMENT VERIFICATION
# =============================================================================
vel_verify_deployment() {
    vel_step "Verifying deployment..."
    
    vel_info "Checking pod status..."
    kubectl get pods -n vel-system
    
    vel_info "Checking services..."
    kubectl get svc -n vel-system
    
    vel_info "Checking ingress..."
    kubectl get ingress -n vel-system || true
    
    # Get load balancer URL
    local lb_url=$(kubectl get svc -n vel-system -o jsonpath='{.items[?(@.spec.type=="LoadBalancer")].status.loadBalancer.ingress[0].hostname}' 2>/dev/null)
    
    if [ -n "${lb_url}" ]; then
        vel_success "Application accessible at: http://${lb_url}"
    fi
    
    vel_success "Deployment verification complete"
}

# =============================================================================
# PRINT DEPLOYMENT SUMMARY
# =============================================================================
vel_print_summary() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}VEL DEPLOYMENT COMPLETE${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Region:        ${VEL_REGION}"
    echo "Cluster:       ${VEL_EKS_NAME}"
    echo "Environment:   ${VEL_ENVIRONMENT}"
    echo "Domain:        ${VEL_DNS_ZONE}"
    echo ""
    echo "CI/CD Pipeline:"
    if [ -n "${VEL_GITHUB_REPO}" ]; then
        echo "  GitHub Repo: ${VEL_GITHUB_REPO}"
        echo "  Branch:      ${VEL_GITHUB_BRANCH}"
        echo "  Pipeline:    vel-${VEL_ENVIRONMENT}-pipeline"
    else
        echo "  Not configured (set VEL_GITHUB_REPO to enable)"
    fi
    echo ""
    echo "Commands:"
    echo "  kubectl get pods -n vel-system    # Check pod status"
    echo "  kubectl logs -n vel-system -l app=vel-trading  # View logs"
    echo "  helm status vel-trading -n vel-system  # Helm status"
    echo ""
    echo "Log file: ${LOG_FILE}"
    echo ""
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================
main() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║     VEL Trading Platform - AWS Automated Deployment          ║"
    echo "║                 Full Infrastructure Setup                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    vel_info "Starting VEL deployment pipeline..."
    vel_info "Log file: ${LOG_FILE}"
    
    # Get AWS Account ID
    export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
    
    vel_check_prerequisites
    vel_verify_aws_auth
    
    # Setup ECR first
    vel_setup_ecr
    
    # Create buildspec if needed
    if [ ! -f "${SCRIPT_DIR}/../buildspec.yml" ]; then
        vel_create_buildspec
    fi
    
    # Setup GitHub CI/CD
    vel_setup_github_cicd
    
    # Provision infrastructure
    vel_provision_infrastructure
    
    # Configure Kubernetes
    vel_configure_kubernetes
    
    # Install monitoring
    vel_install_monitoring
    
    # Setup SSL
    vel_setup_ssl
    
    # Deploy application
    vel_deploy_application
    
    # Verify deployment
    vel_verify_deployment
    
    # Print summary
    vel_print_summary
    
    vel_success "VEL deployment pipeline completed successfully!"
}

# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================
# Handle arguments
case "${1:-deploy}" in
    deploy)
        main
        ;;
    cicd)
        vel_check_prerequisites
        vel_verify_aws_auth
        export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        vel_setup_github_cicd
        ;;
    build)
        vel_check_prerequisites
        vel_verify_aws_auth
        export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        vel_setup_ecr
        vel_create_buildspec
        ;;
    infrastructure)
        vel_check_prerequisites
        vel_verify_aws_auth
        vel_provision_infrastructure
        ;;
    app)
        vel_check_prerequisites
        vel_configure_kubernetes
        vel_deploy_application
        vel_verify_deployment
        ;;
    *)
        echo "Usage: $0 {deploy|cicd|build|infrastructure|app}"
        echo ""
        echo "Commands:"
        echo "  deploy         Full deployment (default)"
        echo "  cicd           Setup GitHub CI/CD pipeline only"
        echo "  build          Setup ECR and buildspec only"
        echo "  infrastructure Provision infrastructure only"
        echo "  app            Deploy application only"
        exit 1
        ;;
esac
