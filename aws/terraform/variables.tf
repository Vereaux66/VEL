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

# =============================================================================
# RDS Configuration
# =============================================================================

variable "vel_db_instance_class" {
  description = "RDS instance class for VEL database"
  type        = string
  default     = "db.r6g.large"
}

variable "vel_db_storage" {
  description = "RDS storage configuration"
  type = object({
    allocated     = number
    max_allocated = number
  })
  default = {
    allocated     = 100
    max_allocated = 500
  }
}

variable "vel_db_name" {
  description = "Database name for VEL"
  type        = string
  default     = "veltrading"
}

variable "vel_db_username" {
  description = "Master username for RDS"
  type        = string
  default     = "veladmin"
}

variable "vel_db_backup_retention" {
  description = "Number of days to retain RDS backups"
  type        = number
  default     = 30
}

variable "vel_db_enable_replica" {
  description = "Enable read replica for RDS"
  type        = bool
  default     = true
}

# =============================================================================
# Redis Configuration
# =============================================================================

variable "vel_redis_endpoint" {
  description = "Redis endpoint for VEL caching"
  type        = string
  default     = "vel-redis.internal"
}

# =============================================================================
# Secrets Manager Configuration
# =============================================================================

variable "vel_enable_secrets_rotation" {
  description = "Enable automatic secrets rotation"
  type        = bool
  default     = false
}

# =============================================================================
# WAF Configuration
# =============================================================================

variable "vel_waf_rate_limit" {
  description = "WAF rate limit (requests per 5 minutes per IP)"
  type        = number
  default     = 2000
}

variable "vel_waf_blocked_countries" {
  description = "List of country codes to block (ISO 3166-1 alpha-2)"
  type        = list(string)
  default     = []
}

variable "vel_waf_allowlisted_ips" {
  description = "List of allowlisted IP addresses"
  type        = list(string)
  default     = []
}

variable "vel_waf_blocklisted_ips" {
  description = "List of blocklisted IP addresses"
  type        = list(string)
  default     = []
}

variable "vel_waf_block_suspicious_ua" {
  description = "Enable blocking of suspicious user agents (use with caution)"
  type        = bool
  default     = false
}
