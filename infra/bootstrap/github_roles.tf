# Primera fase: solo autenticación. No adjuntar permisos administrativos.
# Los permisos de publicación/despliegue se añadirán tras comprobar OIDC.
resource "aws_iam_role" "github_deploy" {
  name                 = "homologaciones-dev-github-deploy"
  description          = "GitHub Actions desde main; inicialmente solo prueba de identidad"
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
  description = "Rol para la prueba OIDC; sin permisos de despliegue en esta fase."
  value       = aws_iam_role.github_deploy.arn
}
