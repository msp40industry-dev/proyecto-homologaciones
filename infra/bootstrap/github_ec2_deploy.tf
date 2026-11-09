locals {
  # Instancia existente de DEV. Si se sustituye deliberadamente, revisar este
  # destino y el workflow antes de habilitar despliegues en la nueva máquina.
  github_deploy_instance_arn = "arn:aws:ec2:eu-west-1:086358667619:instance/i-0cfac93db6ece709a"
  # No permitir AWS-RunShellScript ni documentos arbitrarios: el rol solo podrá
  # ejecutar el documento fijo de deploy_document.tf.
  github_deploy_document_arn = "arn:aws:ssm:eu-west-1:086358667619:document/homologaciones-dev-deploy"
}

resource "aws_iam_role_policy" "github_ec2_deploy" {
  name = "deploy-only-dev-instance"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "StartAndStopOnlyDev"
        Effect   = "Allow"
        Action   = ["ec2:StartInstances", "ec2:StopInstances"]
        Resource = local.github_deploy_instance_arn
      },
      {
        Sid      = "RunOnlyApplicationDeployment"
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = [local.github_deploy_document_arn, local.github_deploy_instance_arn]
      },
      {
        Sid    = "ObserveDeploymentInIreland"
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ssm:DescribeInstanceInformation",
          "ssm:GetCommandInvocation",
        ]
        # Estas operaciones no admiten restricción por ARN; acotar la región.
        Resource = "*"
        Condition = {
          StringEquals = { "aws:RequestedRegion" = "eu-west-1" }
        }
      },
    ]
  })
}
