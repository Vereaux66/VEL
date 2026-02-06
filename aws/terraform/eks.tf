# VEL Trading Platform - Kubernetes Cluster
# Provisions EKS cluster for VEL trading workloads

module "vel_kubernetes" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.vel_eks_cluster_name
  cluster_version = "1.29"

  vpc_id     = module.vel_network.vpc_id
  subnet_ids = module.vel_network.private_subnets

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    vel_workers = {
      name           = "vel-trading-nodes"
      instance_types = [var.vel_node_instance_type]

      min_size     = var.vel_node_scaling.min_nodes
      max_size     = var.vel_node_scaling.max_nodes
      desired_size = var.vel_node_scaling.desired_nodes

      labels = {
        workload = "vel-trading"
      }

      tags = {
        Component = "VEL-Compute"
      }
    }
  }

  tags = {
    Component = "VEL-Kubernetes"
  }
}
