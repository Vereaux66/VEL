# VEL Trading Platform - IAM Configuration
# Creates service account roles for VEL pods

resource "aws_iam_role" "vel_workload_identity" {
  name        = "vel-pod-service-role"
  description = "IAM role for VEL Kubernetes service accounts via IRSA"

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
          }
        }
      }
    ]
  })

  tags = {
    Component = "VEL-Security"
  }
}

# Policy attachment for VEL-specific AWS service access
resource "aws_iam_role_policy" "vel_service_permissions" {
  name = "vel-service-access"
  role = aws_iam_role.vel_workload_identity.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.vel_logs.arn}:*"
      }
    ]
  })
}
