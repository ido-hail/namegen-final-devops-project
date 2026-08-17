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
