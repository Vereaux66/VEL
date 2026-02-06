# VEL Trading Platform - Observability Stack
# CloudWatch resources for VEL logging and monitoring

resource "aws_cloudwatch_log_group" "vel_logs" {
  name              = "/vel-trading/${var.vel_env_name}"
  retention_in_days = 30

  tags = {
    Component = "VEL-Observability"
  }
}

resource "aws_cloudwatch_log_group" "vel_eks_logs" {
  name              = "/aws/eks/${var.vel_eks_cluster_name}/cluster"
  retention_in_days = 14

  tags = {
    Component = "VEL-Observability"
  }
}
