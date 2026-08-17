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
