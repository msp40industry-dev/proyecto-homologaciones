# Acceso de GitHub desde main. Permisos de publicación acotados en github_ecr.tf;
# sin permisos administrativos, de Terraform ni de operación de la EC2.
resource "aws_iam_role" "github_deploy" {
  name                 = "homologaciones-dev-github-deploy"
  description          = "GitHub Actions desde main; publicacion de imagenes en ECR DEV"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:msp40industry-dev/proyecto-homologaciones:ref:refs/heads/main"
        }
      }
    }]
  })

  tags = { Name = "homologaciones-dev-github-deploy" }
}

output "github_deploy_role_arn" {
  description = "Rol OIDC de GitHub para publicar en ECR DEV; no opera la EC2."
  value       = aws_iam_role.github_deploy.arn
}
