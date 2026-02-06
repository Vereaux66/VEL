# VEL Trading Platform - Application Load Balancer Configuration
# Public-facing load balancer with TLS termination and WAF integration

# Application Load Balancer
resource "aws_lb" "vel_api" {
  name               = "vel-api-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.vel_alb.id]
  subnets            = module.vel_network.public_subnets

  enable_deletion_protection = var.vel_env_name == "production" ? true : false
  enable_http2               = true

  access_logs {
    bucket  = aws_s3_bucket.vel_alb_logs.id
    prefix  = "alb-logs"
    enabled = true
  }

  tags = {
    Name        = "vel-api-alb"
    Component   = "VEL-Network"
    Environment = var.vel_env_name
  }
}

# ALB Security Group
resource "aws_security_group" "vel_alb" {
  name_prefix = "vel-alb-"
  description = "Security group for VEL ALB"
  vpc_id      = module.vel_network.vpc_id

  # Allow HTTPS from anywhere
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS from internet"
  }

  # Allow HTTP for redirect
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP for redirect"
  }

  # Allow all outbound to VPC
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vel_network_cidr]
    description = "All traffic to VPC"
  }

  tags = {
    Name        = "vel-alb-sg"
    Component   = "VEL-Network"
    Environment = var.vel_env_name
  }

  lifecycle {
    create_before_destroy = true
  }
}

# HTTPS Listener
resource "aws_lb_listener" "vel_https" {
  load_balancer_arn = aws_lb.vel_api.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.vel_api.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.vel_api.arn
  }
}

# HTTP to HTTPS redirect
resource "aws_lb_listener" "vel_http_redirect" {
  load_balancer_arn = aws_lb.vel_api.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# Target Group for EKS pods
resource "aws_lb_target_group" "vel_api" {
  name        = "vel-api-tg"
  port        = 5000
  protocol    = "HTTP"
  vpc_id      = module.vel_network.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 10
    unhealthy_threshold = 3
  }

  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = false
  }

  tags = {
    Name        = "vel-api-tg"
    Component   = "VEL-Network"
    Environment = var.vel_env_name
  }
}

# ACM Certificate
resource "aws_acm_certificate" "vel_api" {
  domain_name               = var.vel_dns_zone
  subject_alternative_names = ["*.${var.vel_dns_zone}"]
  validation_method         = "DNS"

  tags = {
    Name        = "vel-api-cert"
    Component   = "VEL-Network"
    Environment = var.vel_env_name
  }

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation for certificate
resource "aws_route53_record" "vel_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.vel_api.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.vel.zone_id
}

# Certificate validation
resource "aws_acm_certificate_validation" "vel_api" {
  certificate_arn         = aws_acm_certificate.vel_api.arn
  validation_record_fqdns = [for record in aws_route53_record.vel_cert_validation : record.fqdn]
}

# Route53 zone data source
data "aws_route53_zone" "vel" {
  name         = var.vel_dns_zone
  private_zone = false
}

# Route53 A record for API
resource "aws_route53_record" "vel_api" {
  zone_id = data.aws_route53_zone.vel.zone_id
  name    = var.vel_dns_zone
  type    = "A"

  alias {
    name                   = aws_lb.vel_api.dns_name
    zone_id                = aws_lb.vel_api.zone_id
    evaluate_target_health = true
  }
}

# Route53 A record for API subdomain
resource "aws_route53_record" "vel_api_sub" {
  zone_id = data.aws_route53_zone.vel.zone_id
  name    = "api.${var.vel_dns_zone}"
  type    = "A"

  alias {
    name                   = aws_lb.vel_api.dns_name
    zone_id                = aws_lb.vel_api.zone_id
    evaluate_target_health = true
  }
}

# S3 bucket for ALB access logs
resource "aws_s3_bucket" "vel_alb_logs" {
  bucket        = "vel-alb-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.vel_env_name != "production"

  tags = {
    Name        = "vel-alb-logs"
    Component   = "VEL-Network"
    Environment = var.vel_env_name
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "vel_alb_logs" {
  bucket = aws_s3_bucket.vel_alb_logs.id

  rule {
    id     = "expire-logs"
    status = "Enabled"

    expiration {
      days = 90
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_s3_bucket_policy" "vel_alb_logs" {
  bucket = aws_s3_bucket.vel_alb_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_elb_service_account.main.id}:root"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.vel_alb_logs.arn}/alb-logs/*"
      }
    ]
  })
}

data "aws_elb_service_account" "main" {}

# WAF association with ALB
resource "aws_wafv2_web_acl_association" "vel_api" {
  resource_arn = aws_lb.vel_api.arn
  web_acl_arn  = aws_wafv2_web_acl.vel_api.arn
}
