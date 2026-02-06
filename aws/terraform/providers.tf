# VEL Trading Platform - Terraform Provider Setup
# Configures AWS provider for VEL infrastructure management

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # S3 Backend with DynamoDB State Locking
  # Uncomment the following block for production deployment:
  #
  # backend "s3" {
  #   bucket         = "vel-terraform-state"
  #   key            = "prod/infrastructure.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "vel-terraform-locks"
  #   
  #   # Use workspaces for different environments
  #   # terraform workspace new staging
  #   # terraform workspace select production
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

# Random provider for generating secure passwords and IDs
provider "random" {}
