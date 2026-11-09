# Integración de la EC2 existente con Systems Manager para el futuro despliegue
# desde GitHub. El rol y la instancia siguen gestionados en environments/dev;
# bootstrap solo gestiona esta asociación IAM, sin modificar compute/user_data.
# No duplicar esta asociación en el estado Terraform de environments/dev.
data "aws_iam_role" "app_ec2" {
  name = "homologaciones-dev-ec2"
}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = data.aws_iam_role.app_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
