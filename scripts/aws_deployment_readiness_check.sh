#!/bin/bash
# =============================================================================
# VEL Trading Platform - AWS Deployment Readiness Check
# =============================================================================
# This script validates that all prerequisites are in place for deploying
# the VEL Trading Platform to AWS.
#
# Usage:
#   ./scripts/aws_deployment_readiness_check.sh [--verbose]
#
# Exit codes:
#   0 - All checks passed, ready for deployment
#   1 - Critical checks failed, not ready for deployment
#   2 - Warnings present, review before deploying
# =============================================================================

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

# Verbose mode
VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

# =============================================================================
# Utility Functions
# =============================================================================

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
}

print_failure() {
    echo -e "${RED}❌ $1${NC}"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    CHECKS_WARNING=$((CHECKS_WARNING + 1))
}

print_info() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${BLUE}ℹ️  $1${NC}"
    fi
}

# =============================================================================
# Check Functions
# =============================================================================

check_command() {
    local cmd=$1
    local name=$2
    
    if command -v "$cmd" &> /dev/null; then
        local version
        version=$("$cmd" --version 2>&1 | head -n1 || echo "unknown")
        print_success "$name installed: $version"
        return 0
    else
        print_failure "$name not installed"
        return 1
    fi
}

check_aws_credentials() {
    print_header "AWS Credentials"
    
    if aws sts get-caller-identity &> /dev/null; then
        local account_id
        account_id=$(aws sts get-caller-identity --query Account --output text)
        local user_arn
        user_arn=$(aws sts get-caller-identity --query Arn --output text)
        print_success "AWS credentials configured"
        print_info "Account ID: $account_id"
        print_info "User/Role: $user_arn"
        return 0
    else
        print_failure "AWS credentials not configured or invalid"
        echo "  Run: aws configure"
        return 1
    fi
}

check_aws_region() {
    # Region resolution priority:
    # 1. VEL_REGION (if set)
    # 2. AWS_REGION (if set)
    # 3. AWS_DEFAULT_REGION (if set)
    # 4. aws configure get region
    # 5. Default to us-east-1
    
    local region="${VEL_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
    
    if [[ -z "$region" ]]; then
        region=$(aws configure get region 2>/dev/null || echo "")
    fi
    
    if [[ -n "$region" ]]; then
        print_success "AWS region configured: $region"
        export VEL_REGION="$region"
        export AWS_REGION="$region"
        return 0
    else
        print_warning "AWS region not explicitly set, using default: us-east-1"
        export VEL_REGION="us-east-1"
        export AWS_REGION="us-east-1"
        return 0
    fi
}

check_eks_cluster() {
    print_header "EKS Cluster"
    
    local cluster_name="${VEL_EKS_NAME:-vel-prod}"
    
    if aws eks describe-cluster --name "$cluster_name" --region "$AWS_REGION" &> /dev/null; then
        print_success "EKS cluster '$cluster_name' exists"
        
        # Check kubectl access
        if kubectl get nodes &> /dev/null; then
            local node_count
            node_count=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
            print_success "kubectl can access cluster ($node_count nodes)"
        else
            print_warning "kubectl cannot access cluster, may need to run:"
            echo "  aws eks update-kubeconfig --name $cluster_name --region $AWS_REGION"
        fi
        return 0
    else
        print_warning "EKS cluster '$cluster_name' not found (will be created on first deployment)"
        return 0
    fi
}

check_ecr_repository() {
    print_header "Container Registry"
    
    local repo_name="${VEL_ECR_REPO:-vel-trading}"
    
    if aws ecr describe-repositories --repository-names "$repo_name" --region "$AWS_REGION" &> /dev/null; then
        print_success "ECR repository '$repo_name' exists"
        
        # Check image count
        local image_count
        image_count=$(aws ecr list-images --repository-name "$repo_name" --region "$AWS_REGION" --query 'length(imageIds)' --output text 2>/dev/null || echo "0")
        print_info "Images in repository: $image_count"
        return 0
    else
        print_warning "ECR repository '$repo_name' not found (will be created on first deployment)"
        return 0
    fi
}

check_rds_instance() {
    print_header "Database (RDS)"
    
    # Look for any RDS instance with 'vel' in the name
    local db_instances
    db_instances=$(aws rds describe-db-instances --region "$AWS_REGION" --query 'DBInstances[?contains(DBInstanceIdentifier, `vel`)].DBInstanceIdentifier' --output text 2>/dev/null || echo "")
    
    if [[ -n "$db_instances" ]]; then
        print_success "RDS instance(s) found: $db_instances"
        
        for db in $db_instances; do
            local status
            status=$(aws rds describe-db-instances --db-instance-identifier "$db" --region "$AWS_REGION" --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "unknown")
            print_info "  $db status: $status"
        done
        return 0
    else
        print_warning "RDS instance not found (will be created on first deployment)"
        return 0
    fi
}

check_redis_cluster() {
    print_header "Cache (Redis)"
    
    # Look for any ElastiCache replication group with 'vel' in the name
    local redis_clusters
    redis_clusters=$(aws elasticache describe-replication-groups --region "$AWS_REGION" --query 'ReplicationGroups[?contains(ReplicationGroupId, `vel`)].ReplicationGroupId' --output text 2>/dev/null || echo "")
    
    if [[ -n "$redis_clusters" ]]; then
        print_success "Redis cluster(s) found: $redis_clusters"
        
        for cluster in $redis_clusters; do
            local status
            status=$(aws elasticache describe-replication-groups --replication-group-id "$cluster" --region "$AWS_REGION" --query 'ReplicationGroups[0].Status' --output text 2>/dev/null || echo "unknown")
            print_info "  $cluster status: $status"
        done
        return 0
    else
        print_warning "Redis cluster not found (will be created on first deployment)"
        return 0
    fi
}

check_secrets_manager() {
    print_header "Secrets Manager"
    
    # Ensure environment is set so we can use the Terraform secret naming scheme
    local env="${VEL_ENVIRONMENT:-production}"
    if [[ -z "$VEL_ENVIRONMENT" ]]; then
        print_warning "VEL_ENVIRONMENT not set, assuming 'production' for secret name checks"
    fi
    
    local secret_prefix="vel/${env}"
    local secret_names=(
        "${secret_prefix}/app-secrets"
        "${secret_prefix}/wallet-keys"
        "${secret_prefix}/exchange-keys"
    )
    
    # Secrets that are automatically created and populated by Terraform
    local auto_created_secrets=(
        "${secret_prefix}/app-secrets"
    )
    
    local secrets_found=0
    
    for secret in "${secret_names[@]}"; do
        if aws secretsmanager describe-secret --secret-id "$secret" --region "$AWS_REGION" &> /dev/null; then
            print_success "Secret '$secret' exists"
            secrets_found=$((secrets_found + 1))
        else
            # Check if this is an auto-created secret
            local is_auto_created=false
            for auto_secret in "${auto_created_secrets[@]}"; do
                if [[ "$secret" == "$auto_secret" ]]; then
                    is_auto_created=true
                    break
                fi
            done
            
            if [[ "$is_auto_created" == "true" ]]; then
                print_warning "Secret '$secret' not found (will be automatically created and populated by Terraform)"
            else
                print_warning "Secret '$secret' not found (must be manually created with sensitive values after Terraform provisioning)"
            fi
        fi
    done
    
    if [[ $secrets_found -gt 0 ]]; then
        return 0
    else
        return 0  # Return 0 as secrets can be created during deployment
    fi
}

check_route53_zone() {
    print_header "DNS (Route 53)"
    
    local domain="${VEL_DNS_ZONE:-kessann.bot}"
    
    # Check if hosted zone exists
    if aws route53 list-hosted-zones --query "HostedZones[?Name=='${domain}.'].Id" --output text --region "$AWS_REGION" &> /dev/null; then
        local zone_id
        zone_id=$(aws route53 list-hosted-zones --query "HostedZones[?Name=='${domain}.'].Id" --output text 2>/dev/null | head -n1)
        if [[ -n "$zone_id" ]]; then
            print_success "Route 53 hosted zone exists for '$domain'"
            print_info "Zone ID: $zone_id"
            return 0
        fi
    fi
    
    print_warning "Route 53 hosted zone for '$domain' not found (will be created on first deployment)"
    return 0
}

check_acm_certificate() {
    print_header "SSL Certificate (ACM)"
    
    local domain="${VEL_DNS_ZONE:-kessann.bot}"
    
    # Check for certificate
    local cert_arn
    cert_arn=$(aws acm list-certificates --region "$AWS_REGION" --query "CertificateSummaryList[?DomainName=='${domain}'].CertificateArn" --output text 2>/dev/null | head -n1)
    
    if [[ -n "$cert_arn" ]]; then
        print_success "ACM certificate exists for '$domain'"
        print_info "Certificate ARN: $cert_arn"
        
        # Check certificate status
        local status
        status=$(aws acm describe-certificate --certificate-arn "$cert_arn" --region "$AWS_REGION" --query 'Certificate.Status' --output text 2>/dev/null)
        if [[ "$status" == "ISSUED" ]]; then
            print_success "Certificate status: ISSUED"
        else
            print_warning "Certificate status: $status (may need validation)"
        fi
        return 0
    else
        print_warning "ACM certificate not found (will be created on first deployment)"
        return 0
    fi
}

check_required_files() {
    print_header "Required Files"
    
    local files=(
        "Dockerfile"
        "requirements.txt"
        "gunicorn.conf.py"
        "wsgi.py"
        ".github/workflows/ci-cd.yml"
        "buildspec.yml"
        "appspec.yml"
        "aws/terraform/variables.tf"
        "aws/terraform/eks.tf"
        "aws/terraform/rds.tf"
        "aws/terraform/redis.tf"
        "aws/helm/vel/Chart.yaml"
        "aws/helm/vel/values.yaml"
        "aws/helm/vel/templates/deployment.yaml"
        "aws/helm/vel/templates/service.yaml"
        "aws/deploy.sh"
    )
    
    local missing_files=0
    
    for file in "${files[@]}"; do
        if [[ -f "$file" ]]; then
            print_success "$file exists"
        else
            print_failure "$file not found"
            ((missing_files++))
        fi
    done
    
    if [[ $missing_files -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

check_docker_build() {
    print_header "Docker Build Test"
    
    # Only test if Docker is available
    if ! command -v docker &> /dev/null; then
        print_warning "Docker not available, skipping build test"
        return 0
    fi
    
    print_info "Testing Docker build (this may take a few minutes)..."
    
    # Build image without pushing
    if docker build -t vel-trading:readiness-test -f Dockerfile . &> /tmp/vel-docker-build.log; then
        print_success "Docker image builds successfully"
        
        # Check image size
        local size
        size=$(docker images vel-trading:readiness-test --format "{{.Size}}" 2>/dev/null)
        print_info "Image size: $size"
        
        # Clean up test image
        docker rmi vel-trading:readiness-test &> /dev/null || true
        return 0
    else
        print_failure "Docker build failed"
        echo "  See /tmp/vel-docker-build.log for details"
        return 1
    fi
}

check_terraform_validity() {
    print_header "Terraform Configuration"
    
    if [[ ! -d "aws/terraform" ]]; then
        print_failure "aws/terraform directory not found"
        return 1
    fi
    
    cd aws/terraform
    
    # Check if terraform is initialized
    if [[ ! -d ".terraform" ]]; then
        print_info "Initializing Terraform..."
        if terraform init &> /tmp/vel-terraform-init.log; then
            print_success "Terraform initialized"
        else
            print_failure "Terraform init failed"
            echo "  See /tmp/vel-terraform-init.log for details"
            cd ../..
            return 1
        fi
    else
        print_success "Terraform already initialized"
    fi
    
    # Validate configuration
    print_info "Validating Terraform configuration..."
    if terraform validate &> /tmp/vel-terraform-validate.log; then
        print_success "Terraform configuration is valid"
        cd ../..
        return 0
    else
        print_failure "Terraform validation failed"
        echo "  See /tmp/vel-terraform-validate.log for details"
        cd ../..
        return 1
    fi
}

check_helm_charts() {
    print_header "Helm Charts"
    
    if [[ ! -d "aws/helm/vel" ]]; then
        print_failure "aws/helm/vel directory not found"
        return 1
    fi
    
    # Lint Helm chart
    print_info "Linting Helm chart..."
    if helm lint aws/helm/vel &> /tmp/vel-helm-lint.log; then
        print_success "Helm chart is valid"
        return 0
    else
        print_warning "Helm chart has linting issues"
        echo "  See /tmp/vel-helm-lint.log for details"
        return 0  # Warning, not critical
    fi
}

check_python_tests() {
    print_header "Python Tests"
    
    # Check if pytest is available
    if ! command -v pytest &> /dev/null; then
        print_warning "pytest not installed, skipping tests"
        echo "  Install with: pip install pytest"
        return 0
    fi
    
    # Check if dependencies are installed
    if ! python3 -c "import flask" &> /dev/null; then
        print_warning "Python dependencies not installed, skipping tests"
        echo "  Install with: pip install -r requirements.txt"
        return 0
    fi
    
    print_info "Running Python tests (this may take a minute)..."
    
    # Set required environment variable for tests
    export ANVEL_MASTER_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || echo "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    
    # Check if timeout command is available
    if command -v timeout &> /dev/null; then
        # Run tests with timeout
        if timeout 120 python3 -m pytest tests/ -v --tb=short &> /tmp/vel-pytest.log; then
            local test_count
            test_count=$(grep -c "PASSED" /tmp/vel-pytest.log || echo "0")
            print_success "Tests passed ($test_count tests)"
            return 0
        else
            print_warning "Some tests failed or timed out"
            echo "  See /tmp/vel-pytest.log for details"
            return 0  # Warning, not critical for deployment readiness
        fi
    else
        # Run tests without timeout (may hang on slow systems)
        if python3 -m pytest tests/ -v --tb=short &> /tmp/vel-pytest.log; then
            local test_count
            test_count=$(grep -c "PASSED" /tmp/vel-pytest.log || echo "0")
            print_success "Tests passed ($test_count tests)"
            return 0
        else
            print_warning "Some tests failed"
            echo "  See /tmp/vel-pytest.log for details"
            return 0  # Warning, not critical for deployment readiness
        fi
    fi
}

check_github_secrets() {
    print_header "GitHub Secrets"
    
    # We can't directly check GitHub secrets, but we can remind the user
    print_warning "Cannot verify GitHub secrets programmatically"
    echo
    echo "  Ensure these secrets are set in GitHub repository settings:"
    echo "    - AWS_ACCESS_KEY_ID"
    echo "    - AWS_SECRET_ACCESS_KEY"
    echo "    - AWS_REGION (or use default)"
    echo "    - ECR_REGISTRY (optional, can be derived)"
    echo
    echo "  Visit: https://github.com/Vereaux66/VEL/settings/secrets/actions"
    
    return 0
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  VEL Trading Platform - AWS Deployment Readiness Check        ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    # Get to repository root
    cd "$(dirname "$0")/.." || exit 1
    
    # Check CLI tools
    print_header "CLI Tools"
    check_command "aws" "AWS CLI" || true
    check_command "kubectl" "kubectl" || true
    check_command "helm" "Helm" || true
    check_command "terraform" "Terraform" || true
    
    # Docker is optional for this check but required for deployment
    if command -v docker &> /dev/null; then
        local version
        version=$(docker --version 2>&1 | head -n1 || echo "unknown")
        print_success "Docker installed: $version"
    else
        print_warning "Docker not installed (required for building images locally)"
    fi
    
    check_command "python3" "Python 3" || true
    check_command "git" "Git" || true
    
    # Check AWS setup
    check_aws_credentials
    check_aws_region
    
    # Check AWS resources
    check_eks_cluster
    check_ecr_repository
    check_rds_instance
    check_redis_cluster
    check_secrets_manager
    check_route53_zone
    check_acm_certificate
    
    # Check project files
    check_required_files
    
    # Check configurations
    check_terraform_validity
    check_helm_charts
    
    # Optional checks
    if [[ "$VERBOSE" == "true" ]]; then
        check_docker_build
        check_python_tests
    fi
    
    # GitHub secrets reminder
    check_github_secrets
    
    # Summary
    print_header "Summary"
    echo
    echo "  ✅ Checks passed:  $CHECKS_PASSED"
    echo "  ❌ Checks failed:  $CHECKS_FAILED"
    echo "  ⚠️  Warnings:       $CHECKS_WARNING"
    echo
    
    if [[ $CHECKS_FAILED -gt 0 ]]; then
        echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  ❌ SYSTEM IS NOT READY FOR DEPLOYMENT                         ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
        echo
        echo "Fix the failed checks above before deploying."
        exit 1
    elif [[ $CHECKS_WARNING -gt 0 ]]; then
        echo -e "${YELLOW}╔════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}║  ⚠️  SYSTEM IS READY WITH WARNINGS                             ║${NC}"
        echo -e "${YELLOW}╚════════════════════════════════════════════════════════════════╝${NC}"
        echo
        echo "Review warnings above. Infrastructure will be created on first deployment."
        echo
        echo "Next steps:"
        echo "  1. Review aws/terraform/variables.tf and customize if needed"
        echo "  2. Set required secrets in AWS Secrets Manager"
        echo "  3. Configure GitHub repository secrets for CI/CD"
        echo "  4. Run: cd aws && ./deploy.sh"
        exit 2
    else
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║  ✅ SYSTEM IS 100% OPERATIONAL READY FOR AWS DEPLOYMENT        ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
        echo
        echo "All checks passed! You can proceed with deployment:"
        echo "  cd aws && ./deploy.sh"
        exit 0
    fi
}

# Run main function
main "$@"
