# Solo los modelos ya validados en local. Cambiar esta lista al aprobar otros
# modelos; cambiar .env.dev no concede por sí mismo permisos al rol de la EC2.
locals {
  bedrock_models = toset([
    "anthropic.claude-sonnet-4-6",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
  ])
}

resource "aws_iam_role_policy" "bedrock_invoke" {
  name = "invoke-validated-bedrock-models"
  role = aws_iam_role.ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = flatten([
      for model in sort(tolist(local.bedrock_models)) : [
        {
          Effect = "Allow"
          Action = ["bedrock:InvokeModel", "bedrock:GetInferenceProfile"]
          Resource = [
            "arn:aws:bedrock:eu-west-1:086358667619:inference-profile/eu.${model}"
          ]
        },
        {
          Effect = "Allow"
          Action = ["bedrock:InvokeModel"]
          # El perfil EU puede enrutar a varias regiones europeas. Solo se
          # permite este modelo y a través de su perfil EU desde Irlanda.
          Resource = ["arn:aws:bedrock:eu-*::foundation-model/${model}"]
          Condition = {
            StringEquals = {
              "bedrock:InferenceProfileArn" = "arn:aws:bedrock:eu-west-1:086358667619:inference-profile/eu.${model}"
            }
          }
        }
      ]
    ])
  })
}
