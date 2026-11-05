terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {
    bucket              = "homologaciones-tfstate-086358667619-eu-west-1"
    key                 = "dev/terraform.tfstate"
    region              = "eu-west-1"
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = ["086358667619"]
  }
}

provider "aws" {
  region              = "eu-west-1"
  allowed_account_ids = ["086358667619"]
  default_tags {
    tags = {
      Project     = "homologaciones"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

resource "aws_ecr_repository" "app" {
  for_each             = toset(["frontend", "backend"])
  name                 = "homologaciones-dev/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  encryption_configuration {
    encryption_type = "AES256"
  }
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Elimina únicamente imágenes sin etiqueta pasados siete días. Las imágenes
# etiquetadas se conservan para permitir volver a una versión anterior.
resource "aws_ecr_lifecycle_policy" "untagged" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged images after seven days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 7
      }
      action = { type = "expire" }
    }]
  })
}

output "repository_urls" {
  description = "Destinos para publicar las imágenes validadas."
  value       = { for name, repository in aws_ecr_repository.app : name => repository.repository_url }
}
