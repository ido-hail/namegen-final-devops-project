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
