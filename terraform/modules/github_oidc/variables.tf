variable "role_name" {
  description = "Name of the IAM role assumed by GitHub Actions."
  type        = string
}

variable "github_oidc_subject" {
  description = "Exact GitHub Actions OIDC subject allowed to assume the role."
  type        = string
}

variable "existing_oidc_provider_arn" {
  description = "Existing GitHub OIDC provider ARN, or null to create one."
  type        = string
  nullable    = true
}

variable "ecr_repository_arn" {
  description = "ARN of the ECR repository used by the deployment workflow."
  type        = string
}

variable "eks_cluster_name" {
  description = "Name of the EKS cluster deployed by the workflow."
  type        = string
}

variable "eks_cluster_arn" {
  description = "ARN of the EKS cluster deployed by the workflow."
  type        = string
}

variable "aws_partition" {
  description = "AWS partition discovered at runtime."
  type        = string
}
