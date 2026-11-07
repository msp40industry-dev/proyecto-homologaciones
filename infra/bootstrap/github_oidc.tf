# Identidad compartida de GitHub Actions en DEV. Los roles y sus condiciones de
# confianza delimitarán después qué repositorio y rama pueden obtener permisos.
# Registrar el proveedor por sí solo no concede acceso a recursos AWS.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # Para GitHub, IAM valida el certificado mediante sus CA de confianza.
  # No fijar huellas de certificados que puedan quedar obsoletas.
  tags = { Name = "homologaciones-github-actions" }
}

output "github_oidc_provider_arn" {
  description = "Proveedor de identidades que usarán los roles de GitHub Actions en DEV."
  value       = aws_iam_openid_connect_provider.github.arn
}
