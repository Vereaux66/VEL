# VEL Trading Platform - Terraform State Infrastructure
# Bootstrap resources for state management (run this first)
#
# Usage:
#   cd aws/terraform/bootstrap
#   terraform init
#   terraform apply -var="bucket_suffix=mycompany"
#
# After this is created, update providers.tf to use the S3 backend.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "bucket_suffix" {
  description = "Unique suffix for S3 bucket name (e.g., account ID, company name)"
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "AWS region for state resources"
  type        = string
  default     = "us-east-1"
}

locals {
  # Generate a unique bucket name using account ID if no suffix provided
  bucket_name = var.bucket_suffix != "" ? "vel-terraform-state-${var.bucket_suffix}" : "vel-terraform-state-${data.aws_caller_identity.current.account_id}"
  lock_table_name = var.bucket_suffix != "" ? "vel-terraform-locks-${var.bucket_suffix}" : "vel-terraform-locks"
}

data "aws_caller_identity" "current" {}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "VEL-Trading"
      ManagedBy = "Terraform"
      Purpose   = "StateManagement"
    }
  }
}

# S3 bucket for Terraform state
resource "aws_s3_bucket" "terraform_state" {
  bucket = local.bucket_name

  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name = local.bucket_name
  }
}

# Enable versioning for state recovery
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for state locking
resource "aws_dynamodb_table" "terraform_locks" {
  name         = local.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  # Point-in-time recovery for lock table
  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = local.lock_table_name
  }
}

# Outputs
output "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform state"
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "ARN of the S3 bucket for Terraform state"
  value       = aws_s3_bucket.terraform_state.arn
}

output "lock_table_name" {
  description = "Name of the DynamoDB table for state locking"
  value       = aws_dynamodb_table.terraform_locks.name
}

output "backend_config" {
  description = "Backend configuration to add to providers.tf"
  value       = <<-EOT
    # Add this to your terraform block in providers.tf:
    backend "s3" {
      bucket         = "${aws_s3_bucket.terraform_state.id}"
      key            = "prod/infrastructure.tfstate"
      region         = "us-east-1"
      encrypt        = true
      dynamodb_table = "${aws_dynamodb_table.terraform_locks.name}"
    }
  EOT
}
