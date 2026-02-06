# VEL Trading Platform - Network Infrastructure
# Creates isolated VPC for VEL Kubernetes workloads

locals {
  vel_azs = ["${var.vel_aws_region}a", "${var.vel_aws_region}b", "${var.vel_aws_region}c"]

  vel_private_cidrs = [
    cidrsubnet(var.vel_network_cidr, 8, 1),
    cidrsubnet(var.vel_network_cidr, 8, 2),
    cidrsubnet(var.vel_network_cidr, 8, 3)
  ]

  vel_public_cidrs = [
    cidrsubnet(var.vel_network_cidr, 8, 101),
    cidrsubnet(var.vel_network_cidr, 8, 102),
    cidrsubnet(var.vel_network_cidr, 8, 103)
  ]
}

module "vel_network" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "vel-trading-vpc"
  cidr = var.vel_network_cidr

  azs             = local.vel_azs
  private_subnets = local.vel_private_cidrs
  public_subnets  = local.vel_public_cidrs

  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Component = "VEL-Network"
  }

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}
