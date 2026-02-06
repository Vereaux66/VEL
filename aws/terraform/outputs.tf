# VEL Trading Platform - Terraform Outputs
# Exports key infrastructure identifiers for downstream use

# =============================================================================
# EKS Cluster Outputs
# =============================================================================

output "vel_cluster_name" {
  description = "Name of the VEL EKS cluster"
  value       = module.vel_kubernetes.cluster_name
}

output "vel_cluster_endpoint" {
  description = "API endpoint for VEL Kubernetes cluster"
  value       = module.vel_kubernetes.cluster_endpoint
}

# =============================================================================
# Network Outputs
# =============================================================================

output "vel_vpc_id" {
  description = "ID of the VEL VPC"
  value       = module.vel_network.vpc_id
}

output "vel_private_subnets" {
  description = "Private subnet IDs for VEL workloads"
  value       = module.vel_network.private_subnets
}

output "vel_public_subnets" {
  description = "Public subnet IDs for load balancers"
  value       = module.vel_network.public_subnets
}

# =============================================================================
# Certificate Outputs
# =============================================================================

output "vel_certificate_arn" {
  description = "ARN of the VEL TLS certificate"
  value       = aws_acm_certificate.vel_api.arn
}

# =============================================================================
# Logging Outputs
# =============================================================================

output "vel_log_group" {
  description = "CloudWatch log group for VEL applications"
  value       = aws_cloudwatch_log_group.vel_logs.name
}

output "vel_waf_log_group" {
  description = "CloudWatch log group for WAF logs"
  value       = aws_cloudwatch_log_group.vel_waf_logs.name
}

# =============================================================================
# IAM Outputs
# =============================================================================

output "vel_iam_role_arn" {
  description = "IAM role ARN for VEL pod service accounts"
  value       = aws_iam_role.vel_workload_identity.arn
}

# =============================================================================
# RDS Outputs
# =============================================================================

output "vel_db_endpoint" {
  description = "RDS endpoint for VEL database"
  value       = aws_db_instance.vel_primary.endpoint
  sensitive   = true
}

output "vel_db_identifier" {
  description = "RDS instance identifier"
  value       = aws_db_instance.vel_primary.identifier
}

output "vel_db_replica_endpoint" {
  description = "RDS read replica endpoint"
  value       = length(aws_db_instance.vel_replica) > 0 ? aws_db_instance.vel_replica[0].endpoint : null
  sensitive   = true
}

# =============================================================================
# Secrets Manager Outputs
# =============================================================================

output "vel_app_secrets_arn" {
  description = "ARN of the VEL application secrets"
  value       = aws_secretsmanager_secret.vel_app_secrets.arn
}

output "vel_exchange_keys_arn" {
  description = "ARN of the VEL exchange API keys secret"
  value       = aws_secretsmanager_secret.vel_exchange_keys.arn
}

output "vel_wallet_keys_arn" {
  description = "ARN of the VEL wallet keys secret"
  value       = aws_secretsmanager_secret.vel_wallet_keys.arn
}

# =============================================================================
# WAF Outputs
# =============================================================================

output "vel_waf_acl_arn" {
  description = "ARN of the VEL WAF Web ACL"
  value       = aws_wafv2_web_acl.vel_api.arn
}

output "vel_waf_acl_id" {
  description = "ID of the VEL WAF Web ACL"
  value       = aws_wafv2_web_acl.vel_api.id
}

# =============================================================================
# ALB Outputs
# =============================================================================

output "vel_alb_arn" {
  description = "ARN of the VEL Application Load Balancer"
  value       = aws_lb.vel_api.arn
}

output "vel_alb_dns_name" {
  description = "DNS name of the VEL Application Load Balancer"
  value       = aws_lb.vel_api.dns_name
}

output "vel_api_url" {
  description = "URL of the VEL API"
  value       = "https://${var.vel_dns_zone}"
}
