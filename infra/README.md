# Infraestructura AWS — primera fase DEV

Ejecutar desde PowerShell en la raíz del repositorio. Esta fase prepara S3 para
el estado compartido de Terraform y dos repositorios privados ECR en Irlanda.
No despliega aún la aplicación. Las operaciones apply crean recursos facturables:
S3 cobra almacenamiento y peticiones; ECR cobra el almacenamiento de imágenes.

Las configuraciones comprueban que la cuenta es DEV (086358667619). No reutilizar
este backend para PROD: tendrá configuración y estado en su propia cuenta.

## 1. Acceso temporal desde PowerShell

```powershell
aws login --profile homologaciones-dev
aws sts get-caller-identity --profile homologaciones-dev
```

Comprobar Account = 086358667619 y el rol TeamAdministratorAccess. Para que tanto
Terraform como su backend puedan utilizar las credenciales temporales de aws login,
se usa el proceso de credenciales de AWS CLI mediante un perfil auxiliar. No se
escriben claves en el código ni en los archivos de estado.

```powershell
aws configure set credential_process 'aws configure export-credentials --profile homologaciones-dev --format process' --profile homologaciones-dev-terraform
aws configure set region eu-west-1 --profile homologaciones-dev-terraform
$env:AWS_PROFILE = 'homologaciones-dev-terraform'
aws sts get-caller-identity
```

Verificar que esta última comprobación también devuelve la cuenta DEV. Evitar
variables AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY o AWS_SESSION_TOKEN antiguas
en esta terminal, porque pueden prevalecer sobre el perfil. No imprimir secretos.
Si la sesión caduca, repetir aws login sobre homologaciones-dev.

## 2. Inicializar el bucket de estado (una sola persona, una sola vez)

El primer bloque necesita empezar con estado local porque su bucket todavía no
existe. Hasta completar la migración, conservar el estado local y no ejecutar este
paso simultáneamente en otro equipo. Si el bucket ya existe, comprobar su estado
y propietario antes de continuar; no crear otro ni intentar sobrescribirlo.

```powershell
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/bootstrap plan -out=bootstrap.tfplan
```

Revisar el plan: debe añadir cinco recursos, sin modificar ni eliminar otros.
Después de revisarlo, crear el bucket y su configuración:

```powershell
terraform -chdir=infra/bootstrap apply bootstrap.tfplan
```

El bucket bloquea acceso público, cifra con SSE-S3, guarda versiones y exige HTTPS.
Se usa bloqueo nativo S3: no hace falta crear una tabla DynamoDB.

## 3. Migrar el estado inicial a S3

Solo después de que el apply anterior termine correctamente:

```powershell
Copy-Item infra/bootstrap/backend.tf.example infra/bootstrap/backend.tf
terraform -chdir=infra/bootstrap init -migrate-state
```

Aceptar la copia del estado al backend S3 cuando Terraform lo solicite. Verificar:

```powershell
terraform -chdir=infra/bootstrap plan
```

Debe indicar que no hay cambios. Subir backend.tf y .terraform.lock.hcl a Git.
No subir archivos terraform.tfstate, copias de estado ni planes. Tras la migración,
los demás colaboradores clonan el código y ejecutan init; no repiten el bootstrap
desde cero ni vuelven a copiar la plantilla.

## 4. Preparar los repositorios ECR

```powershell
terraform -chdir=infra/environments/dev init
terraform -chdir=infra/environments/dev validate
terraform -chdir=infra/environments/dev plan -out=dev.tfplan
```

Revisar el plan: debe añadir dos repositorios y dos políticas de limpieza. Después:

```powershell
terraform -chdir=infra/environments/dev apply dev.tfplan
terraform -chdir=infra/environments/dev output repository_urls
```

Repositorios: homologaciones-dev/frontend y homologaciones-dev/backend. Las etiquetas
son inmutables: publicar cada versión con una etiqueta nueva, preferiblemente el
commit Git. No utilizar latest como etiqueta que se sobrescribe. Las imágenes sin
etiqueta caducan a los siete días; las etiquetadas requieren revisar su retención
para controlar el almacenamiento. El escaneo básico no bloquea el despliegue por sí solo.

Conservar en Git los dos archivos .terraform.lock.hcl generados por init para fijar
la versión del proveedor. No ejecutar apply simultáneamente entre colaboradores.
El bloqueo del backend protege frente a escrituras concurrentes; no desactivarlo.

## Próxima fase

Publicar las imágenes ya probadas en ECR y adaptar Compose para descargarlas.
Después, definir EC2, disco, red y permisos. Los secretos, ChromaDB y documentos
no se incluyen en las imágenes ni en el estado de Terraform. La configuración de
PROD y la automatización con GitHub se abordarán en fases posteriores.

Referencias: [backend S3](https://developer.hashicorp.com/terraform/language/backend/s3)
y [repositorios ECR](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_repository).
