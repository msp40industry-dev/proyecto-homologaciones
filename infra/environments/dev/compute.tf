data "aws_availability_zones" "available" {
  state = "available"
}

# Verifica que la AMI proporcionada corresponde a Ubuntu 24.04 amd64 de Canonical.
data "aws_ami" "ubuntu" {
  owners = ["099720109477"]
  filter {
    name   = "image-id"
    values = [var.ubuntu_ami_id]
  }
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

data "aws_key_pair" "admin" {
  key_name = var.ssh_key_name
}

resource "aws_vpc" "app" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "homologaciones-dev" }
}

resource "aws_internet_gateway" "app" {
  vpc_id = aws_vpc.app.id
  tags   = { Name = "homologaciones-dev" }
}

resource "aws_subnet" "app" {
  vpc_id                  = aws_vpc.app.id
  cidr_block              = "10.42.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "homologaciones-dev-public" }
}

resource "aws_route_table" "app" {
  vpc_id = aws_vpc.app.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.app.id
  }
  tags = { Name = "homologaciones-dev-public" }
}

resource "aws_route_table_association" "app" {
  subnet_id      = aws_subnet.app.id
  route_table_id = aws_route_table.app.id
}

resource "aws_security_group" "app" {
  name_prefix = "homologaciones-dev-"
  description = "SSH desde el administrador; web solo al habilitar publicacion"
  vpc_id      = aws_vpc.app.id
  tags        = { Name = "homologaciones-dev" }
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.app.id
  description       = "SSH y tunel privado desde la IPv4 del administrador"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = var.admin_ipv4_cidr
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each          = var.enable_public_web ? toset(["80", "443"]) : toset([])
  security_group_id = aws_security_group.app.id
  description       = "Entrada publica de Caddy"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "internet" {
  security_group_id = aws_security_group.app.id
  description       = "Paquetes Ubuntu, registros Docker y API de modelos"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_iam_role" "ec2" {
  name = "homologaciones-dev-ec2"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecr_pull" {
  name = "read-application-images"
  role = aws_iam_role.ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = [for repository in aws_ecr_repository.app : repository.arn]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "app" {
  name = "homologaciones-dev-ec2"
  role = aws_iam_role.ec2.name
}

# Datos separados del disco de sistema: sustituir la EC2 no debe eliminar el corpus.
resource "aws_ebs_volume" "data" {
  availability_zone = aws_subnet.app.availability_zone
  size              = 10
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "homologaciones-dev-data" }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_instance" "app" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.medium"
  subnet_id                   = aws_subnet.app.id
  vpc_security_group_ids      = [aws_security_group.app.id]
  associate_public_ip_address = true
  key_name                    = data.aws_key_pair.admin.key_name
  iam_instance_profile        = aws_iam_instance_profile.app.name
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    data_volume_id = aws_ebs_volume.data.id
  })
  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
    tags                  = { Name = "homologaciones-dev-system" }
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  credit_specification {
    cpu_credits = "standard"
  }
  tags = { Name = "homologaciones-dev" }
  depends_on = [
    aws_route_table_association.app,
    aws_vpc_security_group_egress_rule.internet,
    aws_iam_role_policy.ecr_pull
  ]
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "data" {
  device_name                    = "/dev/sdf"
  volume_id                      = aws_ebs_volume.data.id
  instance_id                    = aws_instance.app.id
  stop_instance_before_detaching = true
}

output "instance_id" {
  value = aws_instance.app.id
}

output "instance_public_ip" {
  description = "Puede cambiar después de detener y arrancar la EC2."
  value       = aws_instance.app.public_ip
}

output "data_volume_id" {
  value = aws_ebs_volume.data.id
}
