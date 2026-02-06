# VEL Trading Platform - Terraform Provider Setup
# Configures AWS provider for VEL infrastructure management

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Recommended: Configure remote state for team collaboration
  # backend "s3" {
  #   bucket         = "vel-terraform-state"
  #   key            = "prod/infrastructure.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "vel-terraform-locks"
  # }
}

provider "aws" {
  region = var.vel_aws_region

  default_tags {
    tags = {
      Project     = "VEL-Trading"
      ManagedBy   = "Terraform"
      Environment = var.vel_env_name
    }
  }
}
