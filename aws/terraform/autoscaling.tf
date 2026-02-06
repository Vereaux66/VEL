# VEL Trading Platform - Autoscaling Configuration
# Horizontal Pod Autoscaling and EKS node autoscaling policies

# =============================================================================
# EKS Cluster Autoscaler IAM
# =============================================================================

resource "aws_iam_role" "vel_cluster_autoscaler" {
  name        = "vel-cluster-autoscaler-${var.vel_env_name}"
  description = "IAM role for EKS Cluster Autoscaler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.vel_kubernetes.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${module.vel_kubernetes.oidc_provider}:aud" = "sts.amazonaws.com"
            "${module.vel_kubernetes.oidc_provider}:sub" = "system:serviceaccount:kube-system:cluster-autoscaler"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "vel-cluster-autoscaler"
    Component   = "VEL-Compute"
    Environment = var.vel_env_name
  }
}

resource "aws_iam_role_policy" "vel_cluster_autoscaler" {
  name = "vel-cluster-autoscaler-policy"
  role = aws_iam_role.vel_cluster_autoscaler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeScalingActivities",
          "autoscaling:DescribeTags",
          "ec2:DescribeImages",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeLaunchTemplateVersions",
          "ec2:GetInstanceTypesFromInstanceRequirements",
          "eks:DescribeNodegroup"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:ResourceTag/kubernetes.io/cluster/${var.vel_eks_cluster_name}" = "owned"
          }
        }
      }
    ]
  })
}

# =============================================================================
# Application Auto Scaling for ECS (if using ECS)
# =============================================================================

# Note: For EKS, we use Kubernetes HPA manifests. This section shows
# how ECS autoscaling would be configured if using Fargate.

# resource "aws_appautoscaling_target" "vel_ecs" {
#   max_capacity       = var.vel_autoscaling.max_replicas
#   min_capacity       = var.vel_autoscaling.min_replicas
#   resource_id        = "service/${aws_ecs_cluster.vel.name}/${aws_ecs_service.vel.name}"
#   scalable_dimension = "ecs:service:DesiredCount"
#   service_namespace  = "ecs"
# }

# =============================================================================
# Kubernetes HPA Manifests (for reference)
# =============================================================================

# The following local values generate Kubernetes HPA manifests that should
# be applied to the cluster. In practice, these would be in Helm charts.

locals {
  vel_hpa_manifest = {
    apiVersion = "autoscaling/v2"
    kind       = "HorizontalPodAutoscaler"
    metadata = {
      name      = "vel-api-hpa"
      namespace = "vel-trading"
    }
    spec = {
      scaleTargetRef = {
        apiVersion = "apps/v1"
        kind       = "Deployment"
        name       = "vel-api"
      }
      minReplicas = var.vel_autoscaling.min_replicas
      maxReplicas = var.vel_autoscaling.max_replicas
      metrics = [
        {
          type = "Resource"
          resource = {
            name = "cpu"
            target = {
              type               = "Utilization"
              averageUtilization = var.vel_autoscaling.cpu_target_percent
            }
          }
        },
        {
          type = "Resource"
          resource = {
            name = "memory"
            target = {
              type               = "Utilization"
              averageUtilization = var.vel_autoscaling.memory_target_percent
            }
          }
        }
      ]
      behavior = {
        scaleDown = {
          stabilizationWindowSeconds = 300
          policies = [
            {
              type          = "Percent"
              value         = 10
              periodSeconds = 60
            }
          ]
        }
        scaleUp = {
          stabilizationWindowSeconds = 0
          policies = [
            {
              type          = "Percent"
              value         = 100
              periodSeconds = 15
            },
            {
              type          = "Pods"
              value         = 4
              periodSeconds = 15
            }
          ]
          selectPolicy = "Max"
        }
      }
    }
  }

  vel_vpa_manifest = {
    apiVersion = "autoscaling.k8s.io/v1"
    kind       = "VerticalPodAutoscaler"
    metadata = {
      name      = "vel-api-vpa"
      namespace = "vel-trading"
    }
    spec = {
      targetRef = {
        apiVersion = "apps/v1"
        kind       = "Deployment"
        name       = "vel-api"
      }
      updatePolicy = {
        updateMode = "Auto"
      }
      resourcePolicy = {
        containerPolicies = [
          {
            containerName = "*"
            minAllowed = {
              cpu    = "100m"
              memory = "256Mi"
            }
            maxAllowed = {
              cpu    = "4"
              memory = "8Gi"
            }
          }
        ]
      }
    }
  }
}

# Output HPA manifest for deployment
output "vel_hpa_manifest" {
  description = "Kubernetes HPA manifest for VEL API"
  value       = yamlencode(local.vel_hpa_manifest)
}

output "vel_vpa_manifest" {
  description = "Kubernetes VPA manifest for VEL API"
  value       = yamlencode(local.vel_vpa_manifest)
}

# =============================================================================
# CloudWatch Target Tracking Policies (Alternative to K8s native)
# =============================================================================

# If managing scaling via CloudWatch directly instead of K8s HPA

resource "aws_cloudwatch_metric_alarm" "vel_scale_up_alarm" {
  alarm_name          = "vel-scale-up-${var.vel_env_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EKS"
  period              = 60
  statistic           = "Average"
  threshold           = var.vel_autoscaling.cpu_target_percent
  alarm_description   = "Trigger scale-up when CPU > target"
  
  dimensions = {
    ClusterName = var.vel_eks_cluster_name
  }

  tags = {
    Name        = "vel-scale-up"
    Component   = "VEL-Autoscaling"
    Environment = var.vel_env_name
  }
}

resource "aws_cloudwatch_metric_alarm" "vel_scale_down_alarm" {
  alarm_name          = "vel-scale-down-${var.vel_env_name}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 5
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EKS"
  period              = 60
  statistic           = "Average"
  threshold           = var.vel_autoscaling.cpu_target_percent - 20
  alarm_description   = "Trigger scale-down when CPU is low"
  
  dimensions = {
    ClusterName = var.vel_eks_cluster_name
  }

  tags = {
    Name        = "vel-scale-down"
    Component   = "VEL-Autoscaling"
    Environment = var.vel_env_name
  }
}
