variable "aws_region" {
  description = "AWS Region in which the NameGen infrastructure is deployed."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Lowercase project name used as an AWS resource-name prefix."
  type        = string
  default     = "namegen"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block assigned to the NameGen VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "IPv4 CIDR blocks assigned to the two public subnets."
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "Exactly two public subnet CIDR blocks are required."
  }
}

variable "ecr_repository_name" {
  description = "Name of the private ECR repository."
  type        = string
  default     = "namegen"
}

variable "eks_cluster_name" {
  description = "Name of the EKS Auto Mode cluster."
  type        = string
  default     = "namegen-eks"
}

variable "eks_kubernetes_version" {
  description = "Kubernetes version used by EKS."
  type        = string
  default     = "1.35"
}

variable "eks_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public EKS API endpoint."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "github_owner" {
  description = "GitHub account that owns the deployment repository."
  type        = string
  default     = "ido-hail"
}

variable "github_owner_id" {
  description = "Immutable numeric ID of the GitHub repository owner."
  type        = string
  default     = "262130795"
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deployment role."
  type        = string
  default     = "namegen-final-devops-project"
}

variable "github_repository_id" {
  description = "Immutable numeric ID of the GitHub repository."
  type        = string
  default     = "1338080701"
}

variable "github_branch" {
  description = "GitHub branch allowed to assume the deployment role."
  type        = string
  default     = "main"
}

variable "github_oidc_provider_arn" {
  description = "Existing GitHub OIDC provider ARN, or null to create one."
  type        = string
  default     = null
  nullable    = true
}
