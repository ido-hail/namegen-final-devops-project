resource "aws_iam_openid_connect_provider" "github" {
  count = var.existing_oidc_provider_arn == null ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = {
    Name = "github-actions"
  }
}

locals {
  oidc_provider_arn = (
    var.existing_oidc_provider_arn != null
    ? var.existing_oidc_provider_arn
    : aws_iam_openid_connect_provider.github[0].arn
  )
}

resource "aws_iam_role" "github_actions" {
  name        = var.role_name
  description = "Short-lived GitHub Actions role for NameGen image delivery."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = local.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = var.github_oidc_subject
          }
        }
      }
    ]
  })

  tags = {
    Name = var.role_name
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name = "${var.role_name}-deployment"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ECRAuthorization"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "ECRImageDelivery"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeImages",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = var.ecr_repository_arn
      },
      {
        Sid      = "EKSClusterDiscovery"
        Effect   = "Allow"
        Action   = "eks:DescribeCluster"
        Resource = var.eks_cluster_arn
      }
    ]
  })
}

resource "aws_eks_access_entry" "github_actions" {
  cluster_name      = var.eks_cluster_name
  principal_arn     = aws_iam_role.github_actions.arn
  kubernetes_groups = ["namegen-github-deployer"]
  type              = "STANDARD"

  tags = {
    Name = var.role_name
  }
}
