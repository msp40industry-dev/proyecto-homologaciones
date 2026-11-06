# Activar solo después de crear el bucket; ver el paso de migración del README.
terraform {
  backend "s3" {
    bucket              = "homologaciones-tfstate-086358667619-eu-west-1"
    key                 = "bootstrap/terraform.tfstate"
    region              = "eu-west-1"
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = ["086358667619"]
  }
}
