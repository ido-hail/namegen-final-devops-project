data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = "NameGen"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
