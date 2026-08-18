variable "cluster_name" {
  description = "Name of the EKS Auto Mode cluster."
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes control-plane version."
  type        = string
}

variable "subnet_ids" {
  description = "IDs of the two public subnets used by EKS."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) == 2
    error_message = "Exactly two subnet IDs are required for the EKS cluster."
  }
}

variable "public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public Kubernetes API endpoint."
  type        = list(string)
}

variable "aws_partition" {
  description = "AWS partition discovered at runtime."
  type        = string
}
