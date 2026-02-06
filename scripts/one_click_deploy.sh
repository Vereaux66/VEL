#!/bin/bash
# =============================================================================
# VEL Trading Platform - One-Click Deploy Script
# =============================================================================
#
# This script automates the complete deployment of the VEL trading platform
# to AWS infrastructure.
#
# Usage:
#   ./scripts/deploy.sh [environment] [options]
#
# Environments:
#   dev         Development environment
#   staging     Staging environment
#   production  Production environment (requires confirmation)
#
# Options:
#   --skip-terraform    Skip Terraform infrastructure deployment
#   --skip-docker       Skip Docker image build and push
#   --skip-k8s          Skip Kubernetes deployment
#   --dry-run           Show what would be deployed without making changes
#   --force             Skip confirmation prompts
#   --rollback          Rollback to previous deployment
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - kubectl configured for EKS cluster access
#   - Docker installed and running
#   - Terraform >= 1.5 installed
#   - helm >= 3.0 installed
#
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default values
ENVIRONMENT="${1:-staging}"
SKIP_TERRAFORM=false
SKIP_DOCKER=false
SKIP_K8S=false
DRY_RUN=false
FORCE=false
ROLLBACK=false

# AWS Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO="vel-trading"
EKS_CLUSTER="vel-prod"

# Version info
VERSION="${VEL_VERSION:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DEPLOYMENT_ID="deploy-${VERSION}-${TIMESTAMP}"

# =============================================================================
# Utility Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_header() {
    echo ""
    echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}${BOLD}  $1${NC}"
    echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

confirm() {
    if [ "$FORCE" = true ]; then
        return 0
    fi
    
    read -p "$1 [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY]) 
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is required but not installed."
        exit 1
    fi
}

# =============================================================================
# Parse Arguments
# =============================================================================

parse_args() {
    shift # Remove first positional argument (environment)
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-terraform)
                SKIP_TERRAFORM=true
                shift
                ;;
            --skip-docker)
                SKIP_DOCKER=true
                shift
                ;;
            --skip-k8s)
                SKIP_K8S=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            --rollback)
                ROLLBACK=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

show_help() {
    cat << EOF
VEL Trading Platform - One-Click Deploy

Usage: $0 [environment] [options]

Environments:
  dev         Development environment
  staging     Staging environment  
  production  Production environment

Options:
  --skip-terraform    Skip Terraform infrastructure deployment
  --skip-docker       Skip Docker image build and push
  --skip-k8s          Skip Kubernetes deployment
  --dry-run           Show what would be deployed without making changes
  --force             Skip confirmation prompts
  --rollback          Rollback to previous deployment
  -h, --help          Show this help message

Examples:
  $0 staging                        # Deploy to staging
  $0 production --force             # Deploy to production without prompts
  $0 staging --skip-terraform       # Deploy without infrastructure changes
  $0 staging --rollback             # Rollback staging to previous version

EOF
}

# =============================================================================
# Pre-flight Checks
# =============================================================================

preflight_checks() {
    log_header "Pre-flight Checks"
    
    # Check required commands
    log_info "Checking required tools..."
    check_command "aws"
    check_command "docker"
    check_command "kubectl"
    check_command "terraform"
    check_command "helm"
    check_command "git"
    log_success "All required tools available"
    
    # Check AWS credentials
    log_info "Checking AWS credentials..."
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    log_success "AWS Account: ${AWS_ACCOUNT_ID}"
    
    # Check environment
    if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|production)$ ]]; then
        log_error "Invalid environment: ${ENVIRONMENT}. Must be dev, staging, or production."
        exit 1
    fi
    
    # Production safety check
    if [ "$ENVIRONMENT" = "production" ] && [ "$FORCE" = false ]; then
        echo ""
        log_warning "You are about to deploy to PRODUCTION!"
        if ! confirm "Are you sure you want to continue?"; then
            log_info "Deployment cancelled."
            exit 0
        fi
    fi
    
    log_success "Pre-flight checks passed"
}

# =============================================================================
# Terraform Deployment
# =============================================================================

deploy_terraform() {
    if [ "$SKIP_TERRAFORM" = true ]; then
        log_info "Skipping Terraform deployment (--skip-terraform)"
        return 0
    fi
    
    log_header "Infrastructure Deployment (Terraform)"
    
    cd "${PROJECT_ROOT}/aws/terraform"
    
    # Initialize Terraform
    log_info "Initializing Terraform..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would run: terraform init"
    else
        terraform init -upgrade
    fi
    
    # Select workspace
    log_info "Selecting workspace: ${ENVIRONMENT}"
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would select workspace: ${ENVIRONMENT}"
    else
        terraform workspace select "${ENVIRONMENT}" 2>/dev/null || terraform workspace new "${ENVIRONMENT}"
    fi
    
    # Plan
    log_info "Planning infrastructure changes..."
    PLAN_FILE="/tmp/vel-terraform-${ENVIRONMENT}.plan"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would run: terraform plan -var vel_env_name=${ENVIRONMENT}"
    else
        terraform plan \
            -var "vel_env_name=${ENVIRONMENT}" \
            -var "vel_aws_region=${AWS_REGION}" \
            -out="${PLAN_FILE}"
        
        # Show plan summary
        log_info "Review the above plan before applying."
        
        if [ "$FORCE" = false ]; then
            if ! confirm "Apply this infrastructure plan?"; then
                log_info "Infrastructure deployment skipped."
                return 0
            fi
        fi
        
        # Apply
        log_info "Applying infrastructure changes..."
        terraform apply "${PLAN_FILE}"
    fi
    
    log_success "Infrastructure deployment complete"
    cd "${PROJECT_ROOT}"
}

# =============================================================================
# Docker Build and Push
# =============================================================================

deploy_docker() {
    if [ "$SKIP_DOCKER" = true ]; then
        log_info "Skipping Docker build (--skip-docker)"
        return 0
    fi
    
    log_header "Docker Image Build & Push"
    
    ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
    IMAGE_TAG="${ECR_URI}:${VERSION}"
    
    # Login to ECR
    log_info "Authenticating with ECR..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would authenticate with ECR"
    else
        aws ecr get-login-password --region "${AWS_REGION}" | \
            docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    fi
    
    # Create ECR repo if it doesn't exist
    log_info "Ensuring ECR repository exists..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would create ECR repository if needed"
    else
        aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${AWS_REGION}" &>/dev/null || \
            aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}"
    fi
    
    # Build image
    log_info "Building Docker image: ${IMAGE_TAG}"
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would build Docker image"
    else
        docker build \
            -t "${IMAGE_TAG}" \
            -t "${ECR_URI}:latest" \
            -t "${ECR_URI}:${ENVIRONMENT}" \
            --build-arg VERSION="${VERSION}" \
            --build-arg ENVIRONMENT="${ENVIRONMENT}" \
            -f "${PROJECT_ROOT}/Dockerfile" \
            "${PROJECT_ROOT}"
    fi
    
    # Push image
    log_info "Pushing Docker image to ECR..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would push Docker image"
    else
        docker push "${IMAGE_TAG}"
        docker push "${ECR_URI}:latest"
        docker push "${ECR_URI}:${ENVIRONMENT}"
    fi
    
    log_success "Docker image deployed: ${IMAGE_TAG}"
}

# =============================================================================
# Kubernetes Deployment
# =============================================================================

deploy_kubernetes() {
    if [ "$SKIP_K8S" = true ]; then
        log_info "Skipping Kubernetes deployment (--skip-k8s)"
        return 0
    fi
    
    log_header "Kubernetes Deployment"
    
    # Update kubeconfig
    log_info "Configuring kubectl for EKS cluster..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would update kubeconfig"
    else
        aws eks update-kubeconfig \
            --region "${AWS_REGION}" \
            --name "${EKS_CLUSTER}"
    fi
    
    # Create namespace if it doesn't exist
    log_info "Ensuring namespace exists..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would create namespace vel-trading"
    else
        kubectl create namespace vel-trading --dry-run=client -o yaml | kubectl apply -f -
    fi
    
    # Deploy using Helm
    log_info "Deploying with Helm..."
    HELM_CHART="${PROJECT_ROOT}/aws/helm/vel-trading"
    
    ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would run: helm upgrade --install vel-trading"
    else
        helm upgrade --install vel-trading "${HELM_CHART}" \
            --namespace vel-trading \
            --set image.repository="${ECR_URI}" \
            --set image.tag="${VERSION}" \
            --set environment="${ENVIRONMENT}" \
            --set deployment.id="${DEPLOYMENT_ID}" \
            --wait \
            --timeout 10m
    fi
    
    # Verify deployment
    log_info "Verifying deployment..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would verify deployment"
    else
        kubectl rollout status deployment/vel-api -n vel-trading --timeout=5m
    fi
    
    log_success "Kubernetes deployment complete"
}

# =============================================================================
# Rollback
# =============================================================================

perform_rollback() {
    log_header "Rollback Deployment"
    
    log_warning "Rolling back to previous deployment..."
    
    # Rollback Kubernetes deployment
    log_info "Rolling back Kubernetes deployment..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would rollback Kubernetes deployment"
    else
        kubectl rollout undo deployment/vel-api -n vel-trading
        kubectl rollout status deployment/vel-api -n vel-trading --timeout=5m
    fi
    
    log_success "Rollback complete"
}

# =============================================================================
# Post-deployment Validation
# =============================================================================

validate_deployment() {
    log_header "Post-Deployment Validation"
    
    # Get ALB URL
    log_info "Retrieving service endpoint..."
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would retrieve service endpoint"
        return 0
    fi
    
    # Wait for external IP/hostname
    for i in {1..30}; do
        ENDPOINT=$(kubectl get svc vel-api -n vel-trading -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
        if [ -n "$ENDPOINT" ]; then
            break
        fi
        log_info "Waiting for load balancer... ($i/30)"
        sleep 10
    done
    
    if [ -z "$ENDPOINT" ]; then
        log_warning "Could not retrieve service endpoint. Check manually."
        return 1
    fi
    
    # Health check
    log_info "Running health check..."
    HEALTH_URL="https://${ENDPOINT}/health"
    
    for i in {1..5}; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -k "${HEALTH_URL}" 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "200" ]; then
            log_success "Health check passed!"
            log_success "Service endpoint: ${HEALTH_URL}"
            return 0
        fi
        log_info "Health check returned ${HTTP_CODE}, retrying... ($i/5)"
        sleep 10
    done
    
    log_warning "Health check failed. Service may still be starting."
    return 1
}

# =============================================================================
# Summary
# =============================================================================

print_summary() {
    log_header "Deployment Summary"
    
    echo -e "${BOLD}Environment:${NC}    ${ENVIRONMENT}"
    echo -e "${BOLD}Version:${NC}        ${VERSION}"
    echo -e "${BOLD}Deployment ID:${NC}  ${DEPLOYMENT_ID}"
    echo -e "${BOLD}Timestamp:${NC}      $(date)"
    echo ""
    
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}This was a DRY RUN. No changes were made.${NC}"
    else
        echo -e "${GREEN}Deployment completed successfully!${NC}"
    fi
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    log_header "VEL Trading Platform - One-Click Deploy"
    
    # Parse command line arguments
    if [ $# -gt 0 ]; then
        parse_args "$@"
    fi
    
    echo -e "${BOLD}Configuration:${NC}"
    echo "  Environment:     ${ENVIRONMENT}"
    echo "  AWS Region:      ${AWS_REGION}"
    echo "  Version:         ${VERSION}"
    echo "  Dry Run:         ${DRY_RUN}"
    echo "  Skip Terraform:  ${SKIP_TERRAFORM}"
    echo "  Skip Docker:     ${SKIP_DOCKER}"
    echo "  Skip K8s:        ${SKIP_K8S}"
    echo ""
    
    # Handle rollback
    if [ "$ROLLBACK" = true ]; then
        preflight_checks
        perform_rollback
        print_summary
        exit 0
    fi
    
    # Execute deployment steps
    preflight_checks
    deploy_terraform
    deploy_docker
    deploy_kubernetes
    validate_deployment
    print_summary
}

# Run main function with all arguments
main "$@"
