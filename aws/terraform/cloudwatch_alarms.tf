# VEL Trading Platform - CloudWatch Alarms
# Production monitoring alerts for critical system metrics

# =============================================================================
# SNS Topic for Alerts
# =============================================================================

resource "aws_sns_topic" "vel_alerts" {
  name = "vel-alerts-${var.vel_env_name}"

  tags = {
    Name        = "vel-alerts"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_sns_topic_policy" "vel_alerts" {
  arn = aws_sns_topic.vel_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.vel_alerts.arn
      }
    ]
  })
}

# =============================================================================
# EKS Cluster Alarms
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "vel_eks_cpu_high" {
  alarm_name          = "vel-eks-cpu-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "node_cpu_utilization"
  namespace           = "ContainerInsights"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "EKS cluster CPU utilization is above 80%"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    ClusterName = var.vel_eks_cluster_name
  }

  tags = {
    Name        = "vel-eks-cpu-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_eks_memory_high" {
  alarm_name          = "vel-eks-memory-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "node_memory_utilization"
  namespace           = "ContainerInsights"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "EKS cluster memory utilization is above 80%"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    ClusterName = var.vel_eks_cluster_name
  }

  tags = {
    Name        = "vel-eks-memory-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_eks_pods_pending" {
  alarm_name          = "vel-eks-pods-pending-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "pending_pod_count"
  namespace           = "ContainerInsights"
  period              = 300
  statistic           = "Maximum"
  threshold           = 5
  alarm_description   = "Too many pods in pending state"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    ClusterName = var.vel_eks_cluster_name
  }

  tags = {
    Name        = "vel-eks-pods-pending"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

# =============================================================================
# RDS Database Alarms
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "vel_rds_cpu_high" {
  alarm_name          = "vel-rds-cpu-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU utilization is above 80%"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.vel_primary.identifier
  }

  tags = {
    Name        = "vel-rds-cpu-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_rds_storage_low" {
  alarm_name          = "vel-rds-storage-low-${var.vel_env_name}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 10737418240  # 10GB in bytes
  alarm_description   = "RDS free storage space is below 10GB"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.vel_primary.identifier
  }

  tags = {
    Name        = "vel-rds-storage-low"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_rds_connections_high" {
  alarm_name          = "vel-rds-connections-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 400  # 80% of max_connections (500)
  alarm_description   = "RDS connection count is above 400"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.vel_primary.identifier
  }

  tags = {
    Name        = "vel-rds-connections-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_rds_read_latency_high" {
  alarm_name          = "vel-rds-read-latency-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ReadLatency"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 0.020  # 20ms
  alarm_description   = "RDS read latency is above 20ms"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.vel_primary.identifier
  }

  tags = {
    Name        = "vel-rds-read-latency-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

# =============================================================================
# Redis/ElastiCache Alarms
# Note: Using ReplicationGroupId for aggregate metrics across all nodes
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "vel_redis_cpu_high" {
  alarm_name          = "vel-redis-cpu-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "EngineCPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 70
  alarm_description   = "Redis CPU utilization is above 70%"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.vel_redis.id
  }

  tags = {
    Name        = "vel-redis-cpu-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_redis_memory_high" {
  alarm_name          = "vel-redis-memory-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Redis memory usage is above 80%"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.vel_redis.id
  }

  tags = {
    Name        = "vel-redis-memory-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_redis_evictions" {
  alarm_name          = "vel-redis-evictions-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Evictions"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Sum"
  threshold           = 100
  alarm_description   = "Redis is evicting keys due to memory pressure"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    ReplicationGroupId = aws_elasticache_replication_group.vel_redis.id
  }

  tags = {
    Name        = "vel-redis-evictions"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

# =============================================================================
# ALB Alarms
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "vel_alb_5xx_high" {
  alarm_name          = "vel-alb-5xx-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 50
  alarm_description   = "High number of 5XX errors from targets"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    LoadBalancer = aws_lb.vel_api.arn_suffix
  }

  tags = {
    Name        = "vel-alb-5xx-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_alb_latency_high" {
  alarm_name          = "vel-alb-latency-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Average"
  threshold           = 2.0  # 2 seconds
  alarm_description   = "ALB target response time is above 2 seconds"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    LoadBalancer = aws_lb.vel_api.arn_suffix
  }

  tags = {
    Name        = "vel-alb-latency-high"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_alb_unhealthy_hosts" {
  alarm_name          = "vel-alb-unhealthy-hosts-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Unhealthy hosts detected behind ALB"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    LoadBalancer = aws_lb.vel_api.arn_suffix
    TargetGroup  = aws_lb_target_group.vel_api.arn_suffix
  }

  tags = {
    Name        = "vel-alb-unhealthy-hosts"
    Component   = "VEL-Observability"
    Environment = var.vel_env_name
  }
}

# =============================================================================
# WAF Alarms
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "vel_waf_blocked_high" {
  alarm_name          = "vel-waf-blocked-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "BlockedRequests"
  namespace           = "AWS/WAFV2"
  period              = 300
  statistic           = "Sum"
  threshold           = 1000
  alarm_description   = "High number of blocked requests by WAF"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    WebACL = aws_wafv2_web_acl.vel_api.name
    Region = var.vel_aws_region
    Rule   = "ALL"
  }

  tags = {
    Name        = "vel-waf-blocked-high"
    Component   = "VEL-Security"
    Environment = var.vel_env_name
  }
}

# =============================================================================
# Application-Level Alarms (via Custom Metrics)
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "vel_circuit_breaker_open" {
  alarm_name          = "vel-circuit-breaker-open-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "circuit_breaker_state"
  namespace           = "VEL/Trading"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "VEL circuit breaker has been triggered"
  alarm_actions       = [aws_sns_topic.vel_alerts.arn]
  ok_actions          = [aws_sns_topic.vel_alerts.arn]

  dimensions = {
    Environment = var.vel_env_name
    Scope       = "global"
  }

  tags = {
    Name        = "vel-circuit-breaker-open"
    Component   = "VEL-Trading"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_trade_failure_rate" {
  alarm_name          = "vel-trade-failure-rate-high-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 30  # 30% failure rate

  metric_query {
    id          = "failure_rate"
    expression  = "(failed / total) * 100"
    label       = "Trade Failure Rate"
    return_data = true
  }

  metric_query {
    id = "failed"
    metric {
      metric_name = "executions_total"
      namespace   = "VEL/Trading"
      period      = 300
      stat        = "Sum"
      dimensions = {
        Environment = var.vel_env_name
        status      = "failed"
      }
    }
  }

  metric_query {
    id = "total"
    metric {
      metric_name = "executions_total"
      namespace   = "VEL/Trading"
      period      = 300
      stat        = "Sum"
      dimensions = {
        Environment = var.vel_env_name
      }
    }
  }

  alarm_description = "Trade failure rate is above 30%"
  alarm_actions     = [aws_sns_topic.vel_alerts.arn]
  ok_actions        = [aws_sns_topic.vel_alerts.arn]

  tags = {
    Name        = "vel-trade-failure-rate"
    Component   = "VEL-Trading"
    Environment = var.vel_env_name
  }
}

# =============================================================================
# CloudWatch Dashboard
# =============================================================================

resource "aws_cloudwatch_dashboard" "vel_main" {
  dashboard_name = "vel-trading-${var.vel_env_name}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 1
        properties = {
          markdown = "# VEL Trading Platform - ${var.vel_env_name} Dashboard"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "EKS Cluster CPU"
          region = var.vel_aws_region
          metrics = [
            ["ContainerInsights", "node_cpu_utilization", "ClusterName", var.vel_eks_cluster_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "EKS Cluster Memory"
          region = var.vel_aws_region
          metrics = [
            ["ContainerInsights", "node_memory_utilization", "ClusterName", var.vel_eks_cluster_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "RDS Connections"
          region = var.vel_aws_region
          metrics = [
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.vel_primary.identifier]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 7
        width  = 12
        height = 6
        properties = {
          title  = "ALB Requests"
          region = var.vel_aws_region
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.vel_api.arn_suffix]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 7
        width  = 12
        height = 6
        properties = {
          title  = "ALB Response Time"
          region = var.vel_aws_region
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.vel_api.arn_suffix]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 13
        width  = 8
        height = 6
        properties = {
          title  = "WAF Blocked Requests"
          region = var.vel_aws_region
          metrics = [
            ["AWS/WAFV2", "BlockedRequests", "WebACL", aws_wafv2_web_acl.vel_api.name, "Region", var.vel_aws_region, "Rule", "ALL"]
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 13
        width  = 8
        height = 6
        properties = {
          title  = "Redis Memory"
          region = var.vel_aws_region
          metrics = [
            ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage", "ReplicationGroupId", aws_elasticache_replication_group.vel_redis.id]
          ]
        }
      },
      {
        type   = "alarm"
        x      = 16
        y      = 13
        width  = 8
        height = 6
        properties = {
          title = "Alarm Status"
          alarms = [
            aws_cloudwatch_metric_alarm.vel_eks_cpu_high.arn,
            aws_cloudwatch_metric_alarm.vel_rds_cpu_high.arn,
            aws_cloudwatch_metric_alarm.vel_alb_5xx_high.arn,
            aws_cloudwatch_metric_alarm.vel_circuit_breaker_open.arn
          ]
        }
      }
    ]
  })
}
