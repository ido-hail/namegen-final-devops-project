provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "NameGen"
      Environment = "dev"
      ManagedBy   = "Terraform"
      Purpose     = "TerraformState"
    }
  }
}
