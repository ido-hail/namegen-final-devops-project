output "oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC provider."
  value       = local.oidc_provider_arn
}

output "role_name" {
  description = "Name of the GitHub Actions IAM role."
  value       = aws_iam_role.github_actions.name
}

output "role_arn" {
  description = "ARN of the GitHub Actions IAM role."
  value       = aws_iam_role.github_actions.arn
}

output "oidc_subject" {
  description = "Exact GitHub OIDC subject trusted by AWS."
  value       = var.github_oidc_subject
}
