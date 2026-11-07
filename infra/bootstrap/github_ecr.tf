# Los repositorios se gestionan en infra/environments/dev. Aquí solo se concede
# publicación en sus ARN exactos; no se crean, borran ni reconfiguran repositorios.
resource "aws_iam_role_policy" "github_ecr_push" {
  name = "publish-application-images"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RegistryAuthentication"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "PublishOnlyDevApplicationImages"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
        ]
        Resource = [
          "arn:aws:ecr:eu-west-1:086358667619:repository/homologaciones-dev/backend",
          "arn:aws:ecr:eu-west-1:086358667619:repository/homologaciones-dev/frontend",
        ]
      },
    ]
  })
}
