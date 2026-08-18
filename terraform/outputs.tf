output "aws_account_id" {
  description = "AWS Account ID discovered at runtime."
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS Region selected for the deployment."
  value       = var.aws_region
}

output "name_prefix" {
  description = "Common prefix used for project resources."
  value       = local.name_prefix
}

output "vpc_id" {
  description = "ID of the NameGen VPC."
  value       = module.network.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the two public subnets."
  value       = module.network.public_subnet_ids
}

output "availability_zones" {
  description = "Availability Zones used by the public subnets."
  value       = module.network.availability_zones
}

output "ecr_repository_name" {
  description = "Name of the NameGen ECR repository."
  value       = module.ecr.repository_name
}

output "ecr_repository_url" {
  description = "URL of the NameGen ECR repository."
  value       = module.ecr.repository_url
}

output "eks_cluster_name" {
  description = "Name of the EKS Auto Mode cluster."
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Kubernetes API endpoint."
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_role_arn" {
  description = "ARN of the EKS Auto Mode cluster role."
  value       = module.eks.cluster_role_arn
}

output "eks_node_role_arn" {
  description = "ARN of the EKS Auto Mode node role."
  value       = module.eks.node_role_arn
}
