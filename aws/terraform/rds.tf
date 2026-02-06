# VEL Trading Platform - RDS Configuration
# Managed PostgreSQL database for VEL trading operations

# Database subnet group
resource "aws_db_subnet_group" "vel_db" {
  name       = "vel-db-subnet-group"
  subnet_ids = module.vel_network.private_subnets

  tags = {
    Name      = "vel-db-subnet-group"
    Component = "VEL-Database"
  }
}

# Security group for RDS
resource "aws_security_group" "vel_rds" {
  name_prefix = "vel-rds-"
  description = "Security group for VEL RDS instance"
  vpc_id      = module.vel_network.vpc_id

  # Allow PostgreSQL from EKS nodes
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.vel_kubernetes.node_security_group_id]
    description     = "PostgreSQL from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = {
    Name      = "vel-rds-sg"
    Component = "VEL-Database"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# RDS PostgreSQL instance
resource "aws_db_instance" "vel_primary" {
  identifier = "vel-trading-db"

  # Engine configuration
  engine               = "postgres"
  engine_version       = "16.1"
  instance_class       = var.vel_db_instance_class
  allocated_storage    = var.vel_db_storage.allocated
  max_allocated_storage = var.vel_db_storage.max_allocated
  storage_type         = "gp3"
  storage_encrypted    = true
  kms_key_id           = aws_kms_key.vel_db.arn

  # Database configuration
  db_name  = var.vel_db_name
  username = var.vel_db_username
  password = random_password.vel_db_password.result
  port     = 5432

  # Network configuration
  db_subnet_group_name   = aws_db_subnet_group.vel_db.name
  vpc_security_group_ids = [aws_security_group.vel_rds.id]
  publicly_accessible    = false
  multi_az               = var.vel_env_name == "production" ? true : false

  # Backup configuration
  backup_retention_period = var.vel_db_backup_retention
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"
  copy_tags_to_snapshot   = true
  skip_final_snapshot       = var.vel_env_name != "production"
  # Only create final snapshot for production - null for non-production skips snapshot
  final_snapshot_identifier = var.vel_env_name == "production" ? "vel-final-${var.vel_env_name}-${random_id.snapshot_suffix.hex}" : null

  # Performance Insights
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  performance_insights_kms_key_id       = aws_kms_key.vel_db.arn

  # Enhanced monitoring
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.vel_rds_monitoring.arn

  # Parameter group
  parameter_group_name = aws_db_parameter_group.vel_postgres.name

  # Deletion protection for production
  deletion_protection = var.vel_env_name == "production" ? true : false

  # Auto minor version upgrade
  auto_minor_version_upgrade = true

  tags = {
    Name        = "vel-trading-db"
    Component   = "VEL-Database"
    Environment = var.vel_env_name
  }
}

# Random ID for unique snapshot names
resource "random_id" "snapshot_suffix" {
  byte_length = 4
}

# KMS key for RDS encryption
resource "aws_kms_key" "vel_db" {
  description             = "KMS key for VEL RDS encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Name      = "vel-db-kms"
    Component = "VEL-Database"
  }
}

resource "aws_kms_alias" "vel_db" {
  name          = "alias/vel-db"
  target_key_id = aws_kms_key.vel_db.key_id
}

# Random password for database
resource "random_password" "vel_db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# DB parameter group for PostgreSQL optimization
resource "aws_db_parameter_group" "vel_postgres" {
  family = "postgres16"
  name   = "vel-postgres-params"

  # Connection settings
  parameter {
    name  = "max_connections"
    value = "500"
  }

  # Memory settings
  parameter {
    name  = "shared_buffers"
    value = "{DBInstanceClassMemory/4}"
  }

  parameter {
    name  = "effective_cache_size"
    value = "{DBInstanceClassMemory*3/4}"
  }

  # Logging
  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  # SSL enforcement
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = {
    Name      = "vel-postgres-params"
    Component = "VEL-Database"
  }
}

# IAM role for enhanced monitoring
resource "aws_iam_role" "vel_rds_monitoring" {
  name = "vel-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name      = "vel-rds-monitoring-role"
    Component = "VEL-Database"
  }
}

resource "aws_iam_role_policy_attachment" "vel_rds_monitoring" {
  role       = aws_iam_role.vel_rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# Read replica for production (optional)
resource "aws_db_instance" "vel_replica" {
  count = var.vel_env_name == "production" && var.vel_db_enable_replica ? 1 : 0

  identifier = "vel-trading-db-replica"

  replicate_source_db = aws_db_instance.vel_primary.identifier
  instance_class      = var.vel_db_instance_class
  storage_encrypted   = true
  kms_key_id          = aws_kms_key.vel_db.arn

  publicly_accessible    = false
  vpc_security_group_ids = [aws_security_group.vel_rds.id]

  # Performance Insights
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  performance_insights_kms_key_id       = aws_kms_key.vel_db.arn

  # Maintenance
  auto_minor_version_upgrade = true

  tags = {
    Name        = "vel-trading-db-replica"
    Component   = "VEL-Database"
    Environment = var.vel_env_name
  }
}
