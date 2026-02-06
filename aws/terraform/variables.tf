# VEL Trading Platform - Infrastructure Variables
# Customizable parameters for VEL AWS deployment

variable "vel_aws_region" {
  description = "Primary AWS region for VEL infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "vel_eks_cluster_name" {
  description = "Identifier for the VEL Kubernetes cluster"
  type        = string
  default     = "vel-prod"
}

variable "vel_dns_zone" {
  description = "Route53 hosted zone for VEL services"
  type        = string
  default     = "kessann.bot"
}

variable "vel_env_name" {
  description = "Environment identifier (production, staging, dev)"
  type        = string
  default     = "production"
}

variable "vel_network_cidr" {
  description = "CIDR block for VEL VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "vel_node_instance_type" {
  description = "EC2 instance type for EKS worker nodes"
  type        = string
  default     = "m6i.large"
}

variable "vel_node_scaling" {
  description = "Auto-scaling configuration for EKS nodes"
  type = object({
    min_nodes     = number
    max_nodes     = number
    desired_nodes = number
  })
  default = {
    min_nodes     = 6
    max_nodes     = 50
    desired_nodes = 12
  }
}
