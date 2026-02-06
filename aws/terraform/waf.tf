# VEL Trading Platform - WAF Configuration
# Web Application Firewall rules for VEL API protection

# WAF Web ACL for ALB
resource "aws_wafv2_web_acl" "vel_api" {
  name        = "vel-api-waf"
  description = "WAF rules for VEL API Gateway"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Rules - Common Rule Set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "VELCommonRules"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - Known Bad Inputs
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "VELKnownBadInputs"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - SQL Injection
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "VELSQLiRules"
      sampled_requests_enabled   = true
    }
  }

  # Rate limiting rule - API abuse prevention
  rule {
    name     = "VELRateLimitRule"
    priority = 4

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.vel_waf_rate_limit
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "VELRateLimit"
      sampled_requests_enabled   = true
    }
  }

  # Geo-blocking rule (optional, for compliance)
  dynamic "rule" {
    for_each = length(var.vel_waf_blocked_countries) > 0 ? [1] : []

    content {
      name     = "VELGeoBlockRule"
      priority = 5

      action {
        block {}
      }

      statement {
        geo_match_statement {
          country_codes = var.vel_waf_blocked_countries
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "VELGeoBlock"
        sampled_requests_enabled   = true
      }
    }
  }

  # Custom rule - Block suspicious user agents
  rule {
    name     = "VELBlockSuspiciousUserAgents"
    priority = 6

    action {
      block {}
    }

    statement {
      or_statement {
        statement {
          byte_match_statement {
            field_to_match {
              single_header {
                name = "user-agent"
              }
            }
            positional_constraint = "CONTAINS"
            search_string         = "curl/"
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
        statement {
          byte_match_statement {
            field_to_match {
              single_header {
                name = "user-agent"
              }
            }
            positional_constraint = "CONTAINS"
            search_string         = "python-requests"
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "VELSuspiciousUA"
      sampled_requests_enabled   = true
    }
  }

  # IP reputation rule
  rule {
    name     = "AWSManagedRulesAmazonIpReputationList"
    priority = 7

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "VELIpReputation"
      sampled_requests_enabled   = true
    }
  }

  # Bot Control rule
  rule {
    name     = "AWSManagedRulesBotControlRuleSet"
    priority = 8

    override_action {
      count {}  # Count mode initially, switch to none for enforcement
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesBotControlRuleSet"
        vendor_name = "AWS"

        managed_rule_group_configs {
          aws_managed_rules_bot_control_rule_set {
            inspection_level = "COMMON"
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "VELBotControl"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "VELWebACL"
    sampled_requests_enabled   = true
  }

  tags = {
    Name        = "vel-api-waf"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}

# WAF logging configuration
resource "aws_wafv2_web_acl_logging_configuration" "vel_api" {
  log_destination_configs = [aws_cloudwatch_log_group.vel_waf_logs.arn]
  resource_arn            = aws_wafv2_web_acl.vel_api.arn

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior = "KEEP"
      condition {
        action_condition {
          action = "BLOCK"
        }
      }
      requirement = "MEETS_ALL"
    }

    filter {
      behavior = "KEEP"
      condition {
        action_condition {
          action = "COUNT"
        }
      }
      requirement = "MEETS_ALL"
    }
  }
}

# CloudWatch log group for WAF logs
resource "aws_cloudwatch_log_group" "vel_waf_logs" {
  name              = "aws-waf-logs-vel-${var.vel_env_name}"
  retention_in_days = 30

  tags = {
    Name        = "vel-waf-logs"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}

# IP set for allowlisting (e.g., office IPs for admin access)
resource "aws_wafv2_ip_set" "vel_allowlist" {
  name               = "vel-ip-allowlist"
  description        = "Allowlisted IPs for VEL admin access"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = var.vel_waf_allowlisted_ips

  tags = {
    Name        = "vel-ip-allowlist"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}

# IP set for blocklisting
resource "aws_wafv2_ip_set" "vel_blocklist" {
  name               = "vel-ip-blocklist"
  description        = "Blocklisted IPs for VEL"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = var.vel_waf_blocklisted_ips

  tags = {
    Name        = "vel-ip-blocklist"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}
