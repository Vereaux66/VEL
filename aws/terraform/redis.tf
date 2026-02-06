# VEL Trading Platform - Redis/ElastiCache Configuration
# High-availability Redis cluster for caching and session management

# ElastiCache subnet group
resource "aws_elasticache_subnet_group" "vel_redis" {
  name       = "vel-redis-subnet-group"
  subnet_ids = module.vel_network.private_subnets

  tags = {
    Name      = "vel-redis-subnet-group"
    Component = "VEL-Cache"
  }
}

# Security group for Redis
resource "aws_security_group" "vel_redis" {
  name_prefix = "vel-redis-"
  description = "Security group for VEL Redis cluster"
  vpc_id      = module.vel_network.vpc_id

  # Allow Redis from EKS nodes
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.vel_kubernetes.node_security_group_id]
    description     = "Redis from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = {
    Name      = "vel-redis-sg"
    Component = "VEL-Cache"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Redis parameter group
resource "aws_elasticache_parameter_group" "vel_redis" {
  name   = "vel-redis-params"
  family = "redis7"

  # Connection settings
  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }

  parameter {
    name  = "notify-keyspace-events"
    value = "Ex"
  }

  # Persistence settings (AOF for durability)
  parameter {
    name  = "appendonly"
    value = "yes"
  }

  tags = {
    Name      = "vel-redis-params"
    Component = "VEL-Cache"
  }
}

# Redis replication group (cluster mode disabled for simplicity)
resource "aws_elasticache_replication_group" "vel_redis" {
  replication_group_id = "vel-redis"
  description          = "VEL Redis cluster for caching and sessions"

  # Engine configuration
  engine               = "redis"
  engine_version       = "7.0"
  node_type            = var.vel_redis_node_type
  port                 = 6379
  parameter_group_name = aws_elasticache_parameter_group.vel_redis.name

  # Cluster configuration (single shard with replicas)
  num_cache_clusters = var.vel_env_name == "production" ? 3 : 1

  # Network configuration
  subnet_group_name  = aws_elasticache_subnet_group.vel_redis.name
  security_group_ids = [aws_security_group.vel_redis.id]

  # High availability
  automatic_failover_enabled = var.vel_env_name == "production" ? true : false
  multi_az_enabled           = var.vel_env_name == "production" ? true : false

  # Encryption
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = aws_kms_key.vel_redis.arn
  auth_token                 = random_password.vel_redis_auth.result

  # Maintenance
  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_window          = "04:00-05:00"
  snapshot_retention_limit = var.vel_env_name == "production" ? 7 : 1
  auto_minor_version_upgrade = true

  # Logging
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.vel_redis_logs.name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "slow-log"
  }

  tags = {
    Name        = "vel-redis"
    Component   = "VEL-Cache"
    Environment = var.vel_env_name
  }
}

# KMS key for Redis encryption
resource "aws_kms_key" "vel_redis" {
  description             = "KMS key for VEL Redis encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Name      = "vel-redis-kms"
    Component = "VEL-Cache"
  }
}

resource "aws_kms_alias" "vel_redis" {
  name          = "alias/vel-redis"
  target_key_id = aws_kms_key.vel_redis.key_id
}

# Random password for Redis AUTH
# Note: ElastiCache AUTH tokens support alphanumeric and some special characters
# but have restrictions on !@#$%^&*()_+ - using only allowed characters
resource "random_password" "vel_redis_auth" {
  length           = 32
  special          = true
  override_special = "!&#$^<>-"  # Characters allowed by ElastiCache
}

# CloudWatch log group for Redis logs
resource "aws_cloudwatch_log_group" "vel_redis_logs" {
  name              = "/vel-trading/${var.vel_env_name}/redis"
  retention_in_days = 30

  tags = {
    Name      = "vel-redis-logs"
    Component = "VEL-Cache"
  }
}

# Store Redis auth token in Secrets Manager
resource "aws_secretsmanager_secret" "vel_redis_auth" {
  name                    = "vel/${var.vel_env_name}/redis-auth"
  description             = "Redis AUTH token for VEL"
  recovery_window_in_days = var.vel_env_name == "production" ? 30 : 7
  kms_key_id              = aws_kms_key.vel_secrets.arn

  tags = {
    Name        = "vel-redis-auth"
    Component   = "VEL-Cache"
    Environment = var.vel_env_name
  }
}

resource "aws_secretsmanager_secret_version" "vel_redis_auth" {
  secret_id = aws_secretsmanager_secret.vel_redis_auth.id
  secret_string = jsonencode({
    AUTH_TOKEN = random_password.vel_redis_auth.result
    HOST       = aws_elasticache_replication_group.vel_redis.primary_endpoint_address
    PORT       = "6379"
    URL        = "rediss://:${random_password.vel_redis_auth.result}@${aws_elasticache_replication_group.vel_redis.primary_endpoint_address}:6379"
  })
}
