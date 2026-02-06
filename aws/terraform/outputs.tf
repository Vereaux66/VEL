# VEL Trading Platform - Terraform Outputs
# Exports key infrastructure identifiers for downstream use

output "vel_cluster_name" {
  description = "Name of the VEL EKS cluster"
  value       = module.vel_kubernetes.cluster_name
}

output "vel_cluster_endpoint" {
  description = "API endpoint for VEL Kubernetes cluster"
  value       = module.vel_kubernetes.cluster_endpoint
}

output "vel_vpc_id" {
  description = "ID of the VEL VPC"
  value       = module.vel_network.vpc_id
}

output "vel_private_subnets" {
  description = "Private subnet IDs for VEL workloads"
  value       = module.vel_network.private_subnets
}

output "vel_certificate_arn" {
  description = "ARN of the VEL TLS certificate"
  value       = aws_acm_certificate.vel_tls.arn
}

output "vel_log_group" {
  description = "CloudWatch log group for VEL applications"
  value       = aws_cloudwatch_log_group.vel_logs.name
}

output "vel_iam_role_arn" {
  description = "IAM role ARN for VEL pod service accounts"
  value       = aws_iam_role.vel_workload_identity.arn
}
