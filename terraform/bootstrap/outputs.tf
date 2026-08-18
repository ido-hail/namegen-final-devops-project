output "state_bucket_name" {
  description = "Name of the S3 bucket used for Terraform remote state."
  value       = aws_s3_bucket.terraform_state.id
}

output "aws_account_id" {
  description = "AWS Account ID discovered at runtime."
  value       = data.aws_caller_identity.current.account_id
}
