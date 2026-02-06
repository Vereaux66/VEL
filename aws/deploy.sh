#!/usr/bin/env bash
# VEL Trading Platform - AWS Deployment Orchestrator
# Automates infrastructure provisioning and application deployment
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# VEL-specific configuration
export VEL_REGION="${VEL_REGION:-us-east-1}"
export VEL_EKS_NAME="${VEL_EKS_NAME:-vel-prod}"
export VEL_DNS_ZONE="${VEL_DNS_ZONE:-kessann.bot}"

vel_log() {
    printf "[%s] VEL-DEPLOY: %s\n" "$(date '+%H:%M:%S')" "$1"
}

vel_check_prerequisites() {
    vel_log "Checking deployment prerequisites..."
    command -v aws >/dev/null 2>&1 || { vel_log "ERROR: aws cli required"; exit 1; }
    command -v terraform >/dev/null 2>&1 || { vel_log "ERROR: terraform required"; exit 1; }
    command -v helm >/dev/null 2>&1 || { vel_log "ERROR: helm required"; exit 1; }
    command -v kubectl >/dev/null 2>&1 || { vel_log "ERROR: kubectl required"; exit 1; }
}

vel_verify_aws_auth() {
    vel_log "🔐 Authenticating with AWS..."
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        vel_log "ERROR: Invalid AWS credentials"
        exit 1
    fi
    vel_log "AWS authentication successful"
}

vel_provision_infrastructure() {
    vel_log "📦 Provisioning VEL cloud infrastructure..."
    cd "${SCRIPT_DIR}/terraform"
    terraform init -input=false -upgrade
    terraform plan -out="vel_plan_${TIMESTAMP}.tfplan"
    terraform apply -auto-approve "vel_plan_${TIMESTAMP}.tfplan"
    rm -f "vel_plan_${TIMESTAMP}.tfplan"
}

vel_configure_kubernetes() {
    vel_log "🧭 Configuring Kubernetes access..."
    aws eks update-kubeconfig \
        --region "${VEL_REGION}" \
        --name "${VEL_EKS_NAME}" \
        --alias "vel-cluster"
}

vel_install_monitoring() {
    vel_log "📊 Setting up cluster monitoring..."
    kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
}

vel_deploy_application() {
    vel_log "🚀 Deploying VEL trading application..."
    helm upgrade --install vel-trading "${SCRIPT_DIR}/helm/vel" \
        --namespace vel-system \
        --create-namespace \
        --set global.domain="${VEL_DNS_ZONE}" \
        --wait \
        --timeout 10m
}

main() {
    vel_log "Starting VEL deployment pipeline..."
    vel_check_prerequisites
    vel_verify_aws_auth
    vel_provision_infrastructure
    vel_configure_kubernetes
    vel_install_monitoring
    vel_deploy_application
    vel_log "✅ VEL deployment pipeline completed"
}

main "$@"
