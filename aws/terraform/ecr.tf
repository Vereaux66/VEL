# VEL Trading Platform - Elastic Container Registry
# Container image repository for VEL trading services

resource "aws_ecr_repository" "vel_trading" {
  name                 = "vel-trading"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = "vel-trading"
    Component   = "VEL-Container-Registry"
    Environment = var.vel_env_name
  }
}

resource "aws_ecr_repository" "vel_rust_gateway" {
  name                 = "vel-rust-gateway"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = "vel-rust-gateway"
    Component   = "VEL-Container-Registry"
    Environment = var.vel_env_name
  }
}

# Lifecycle policy to clean up old images
resource "aws_ecr_lifecycle_policy" "vel_trading_lifecycle" {
  repository = aws_ecr_repository.vel_trading.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 30 production images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["prod", "release"]
          countType     = "imageCountMoreThan"
          countNumber   = 30
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last 10 staging images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["staging", "stage"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 3
        description  = "Remove untagged images older than 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 4
        description  = "Keep only last 50 dev images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["dev", "develop"]
          countType     = "imageCountMoreThan"
          countNumber   = 50
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# Output ECR repository URLs
output "ecr_trading_repository_url" {
  description = "ECR repository URL for VEL trading service"
  value       = aws_ecr_repository.vel_trading.repository_url
}

output "ecr_gateway_repository_url" {
  description = "ECR repository URL for VEL Rust gateway"
  value       = aws_ecr_repository.vel_rust_gateway.repository_url
}
