locals {
  # El documento lleva los Compose de esta configuración Terraform. Si cambian,
  # aplicar también la nueva versión del documento antes de desplegar imágenes.
  deploy_compose_bundle = {
    "compose.ec2.yml"    = file("${path.module}/../../compose.ec2.yml")
    "compose.public.yml" = file("${path.module}/../../compose.public.yml")
  }
}

resource "aws_ssm_document" "deploy_dev" {
  name            = "homologaciones-dev-deploy"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Actualizar frontend/backend DEV desde ECR conservando datos y secretos locales"
    parameters = {
      ImageTag = {
        type              = "String"
        description       = "Etiqueta generada por GitHub Actions para las dos imagenes"
        interpolationType = "ENV_VAR"
        allowedPattern    = "^sha-[0-9a-f]{40}-[0-9]+-[0-9]+$"
      }
    }
    mainSteps = [{
      action       = "aws:runShellScript"
      name         = "deployApplication"
      precondition = { StringEquals = ["platformType", "Linux"] }
      inputs = {
        timeoutSeconds = "1800"
        runCommand = [join("\n", [
          "set -eu",
          "python3 - <<'HOMOLOGACIONES_DEPLOY'",
          "import base64, json",
          "_DEPLOY_BUNDLE = json.loads(base64.b64decode('${base64encode(jsonencode(local.deploy_compose_bundle))}'))",
          replace(file("${path.module}/../../deploy/remote_deploy.py"), "\r\n", "\n"),
          "HOMOLOGACIONES_DEPLOY",
        ])]
      }
    }]
  })

  tags = { Name = "homologaciones-dev-deploy" }
}

output "dev_deploy_document_name" {
  description = "Documento SSM de despliegue; ejecutarlo requiere permisos sobre el documento y la EC2."
  value       = aws_ssm_document.deploy_dev.name
}
