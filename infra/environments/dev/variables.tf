variable "ssh_key_name" {
  description = "Nombre de una clave EC2 ya creada en DEV, región Irlanda. Nunca introducir el PEM."
  type        = string
  validation {
    condition     = length(trimspace(var.ssh_key_name)) > 0
    error_message = "Indicar el nombre de la clave EC2 de DEV."
  }
}

variable "admin_ipv4_cidr" {
  description = "IPv4 pública del administrador con /32; único origen permitido para SSH."
  type        = string
  validation {
    condition     = can(cidrnetmask(var.admin_ipv4_cidr)) && can(regex("/32$", var.admin_ipv4_cidr))
    error_message = "Utilizar una IPv4 válida con máscara /32, no acceso SSH abierto."
  }
}

variable "ubuntu_ami_id" {
  description = "AMI Ubuntu Server 24.04 amd64 de Canonical en Irlanda; fijarla para evitar cambios implícitos."
  type        = string
  validation {
    condition     = can(regex("^ami-[0-9a-f]{17}$", var.ubuntu_ami_id))
    error_message = "Indicar un identificador AMI válido de 17 caracteres hexadecimales."
  }
}

variable "enable_public_web" {
  description = "Abrir 80/443 cuando estén preparados Caddy, contraseña y dominio. Inicialmente false."
  type        = bool
  default     = false
}
