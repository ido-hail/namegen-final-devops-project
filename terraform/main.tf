data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = "NameGen"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

module "network" {
  source = "./modules/network"

  name_prefix         = local.name_prefix
  vpc_cidr            = var.vpc_cidr
  public_subnet_cidrs = var.public_subnet_cidrs
  availability_zones  = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "ecr" {
  source = "./modules/ecr"

  repository_name = var.ecr_repository_name
}

module "eks" {
  source = "./modules/eks"

  cluster_name        = var.eks_cluster_name
  kubernetes_version  = var.eks_kubernetes_version
  subnet_ids          = module.network.public_subnet_ids
  public_access_cidrs = var.eks_public_access_cidrs
  aws_partition       = data.aws_partition.current.partition
}

locals {
  github_oidc_subject = "repo:${var.github_owner}@${var.github_owner_id}/${var.github_repository}@${var.github_repository_id}:ref:refs/heads/${var.github_branch}"
}

module "github_oidc" {
  source = "./modules/github_oidc"

  role_name                  = "${var.project_name}-github-actions-role"
  github_oidc_subject        = local.github_oidc_subject
  existing_oidc_provider_arn = var.github_oidc_provider_arn
  ecr_repository_arn         = module.ecr.repository_arn
  eks_cluster_name           = module.eks.cluster_name
  eks_cluster_arn            = module.eks.cluster_arn
  aws_partition              = data.aws_partition.current.partition
}
