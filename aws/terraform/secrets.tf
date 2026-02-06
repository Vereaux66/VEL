# VEL Trading Platform - AWS Secrets Manager Configuration
# Centralized secrets management for VEL infrastructure

# Primary secrets store for VEL application
resource "aws_secretsmanager_secret" "vel_app_secrets" {
  name                    = "vel/${var.vel_env_name}/app-secrets"
  description             = "VEL application secrets including API keys and credentials"
  recovery_window_in_days = var.vel_env_name == "production" ? 30 : 7
  kms_key_id              = aws_kms_key.vel_secrets.arn

  tags = {
    Name        = "vel-app-secrets"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}

# Secret version with initial values
resource "aws_secretsmanager_secret_version" "vel_app_secrets" {
  secret_id = aws_secretsmanager_secret.vel_app_secrets.id
  secret_string = jsonencode({
    # Database credentials
    DB_HOST     = aws_db_instance.vel_primary.endpoint
    DB_PORT     = "5432"
    DB_NAME     = var.vel_db_name
    DB_USER     = var.vel_db_username
    DB_PASSWORD = random_password.vel_db_password.result

    # Application secrets (generated)
    FLASK_SECRET_KEY = random_password.vel_flask_secret.result
    JWT_SECRET_KEY   = random_password.vel_jwt_secret.result

    # Redis configuration
    REDIS_HOST = var.vel_redis_endpoint
    REDIS_PORT = "6379"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Separate secret for exchange API keys (manually populated)
resource "aws_secretsmanager_secret" "vel_exchange_keys" {
  name                    = "vel/${var.vel_env_name}/exchange-keys"
  description             = "Exchange API keys for VEL trading operations"
  recovery_window_in_days = var.vel_env_name == "production" ? 30 : 7
  kms_key_id              = aws_kms_key.vel_secrets.arn

  tags = {
    Name        = "vel-exchange-keys"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}

# Separate secret for wallet keys (manually populated)
resource "aws_secretsmanager_secret" "vel_wallet_keys" {
  name                    = "vel/${var.vel_env_name}/wallet-keys"
  description             = "Wallet private keys for VEL DEX operations"
  recovery_window_in_days = var.vel_env_name == "production" ? 30 : 7
  kms_key_id              = aws_kms_key.vel_secrets.arn

  tags = {
    Name        = "vel-wallet-keys"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}

# KMS key for secrets encryption
resource "aws_kms_key" "vel_secrets" {
  description             = "KMS key for VEL Secrets Manager encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow EKS pods to use key"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.vel_workload_identity.arn
        }
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name      = "vel-secrets-kms"
    Component = "VEL-Security"
  }
}

resource "aws_kms_alias" "vel_secrets" {
  name          = "alias/vel-secrets"
  target_key_id = aws_kms_key.vel_secrets.key_id
}

# Random passwords for application secrets
resource "random_password" "vel_flask_secret" {
  length           = 64
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_password" "vel_jwt_secret" {
  length           = 64
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# IAM policy for EKS pods to access secrets
resource "aws_iam_role_policy" "vel_secrets_access" {
  name = "vel-secrets-access"
  role = aws_iam_role.vel_workload_identity.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.vel_app_secrets.arn,
          aws_secretsmanager_secret.vel_exchange_keys.arn,
          aws_secretsmanager_secret.vel_wallet_keys.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.vel_secrets.arn
      }
    ]
  })
}

# Secrets rotation configuration (optional)
resource "aws_secretsmanager_secret_rotation" "vel_app_secrets" {
  count = var.vel_enable_secrets_rotation ? 1 : 0

  secret_id           = aws_secretsmanager_secret.vel_app_secrets.id
  rotation_lambda_arn = aws_lambda_function.vel_secret_rotation[0].arn

  rotation_rules {
    automatically_after_days = 90
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
