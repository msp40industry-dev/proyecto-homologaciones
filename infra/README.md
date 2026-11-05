# Infraestructura y despliegue AWS — DEV

Ejecutar desde PowerShell en la raíz del repositorio. Esta guía prepara S3 para
el estado compartido, ECR y el host EC2 de DEV en Irlanda. La preparación del host
no instala los datos ni arranca la aplicación; los apartados 7 y 8 cubren esos pasos.
Las operaciones apply crean recursos
facturables: S3, ECR y, al aplicar el apartado 6, EC2, discos e IPv4 pública.

Las configuraciones comprueban que la cuenta es DEV (086358667619). No reutilizar
este backend para PROD: tendrá configuración y estado en su propia cuenta.

**DEV ya está desplegado.** Los pasos de creación se conservan para reproducir y
entender el proceso; al incorporarse al entorno existente, no repetir bootstrap
ni migración. Comprobar la cuenta, inicializar con el backend compartido y revisar
el plan antes de cualquier cambio. Terraform no lee automáticamente subcarpetas:
cada `-chdir` selecciona una configuración y su estado.

| Necesidad | Apartado |
|---|---|
| Acceso y credenciales temporales | [1. Acceso](#1-acceso-temporal-desde-powershell) |
| Publicar imágenes desde Windows | [5. ECR](#5-autenticación-de-docker-en-windows-y-uso-de-ecr) |
| Crear o revisar la máquina | [6. Host EC2](#6-preparar-el-host-ec2-de-dev) |
| Copiar datos y arrancar en privado | [7. Instalación inicial](#7-transferencia-inicial-y-arranque-privado) |
| Configurar URL y Caddy | [8. Publicación](#8-publicación-con-duckdns-https-y-contraseña) |
| Actualizar, pausar o reanudar | [9. Operación](#9-operación-y-actualizaciones) |
| Resolver problemas | [10. Diagnóstico](#10-diagnóstico-del-despliegue-realizado) |
| Consultar qué se desplegó | [11. Registro](#11-registro-y-próximos-pasos) |

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

Al abrir otra terminal, volver a seleccionar `$env:AWS_PROFILE`. Si las herramientas
se instalaron en estas rutas y la terminal no las encuentra, recuperar el Path de
la sesión (y añadir las carpetas al Path del usuario para próximas sesiones):

```powershell
$env:Path += ';C:\Tools\Terraform;C:\Tools\ECR'
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
terraform "-chdir=infra/bootstrap" init
terraform "-chdir=infra/bootstrap" validate
terraform "-chdir=infra/bootstrap" plan "-out=bootstrap.tfplan"
```

Revisar el plan: debe añadir cinco recursos, sin modificar ni eliminar otros.
Después de revisarlo, crear el bucket y su configuración:

```powershell
terraform "-chdir=infra/bootstrap" apply "bootstrap.tfplan"
```

El bucket bloquea acceso público, cifra con SSE-S3, guarda versiones y exige HTTPS.
Se usa bloqueo nativo S3: no hace falta crear una tabla DynamoDB.

## 3. Migrar el estado inicial a S3

Solo después de que el apply anterior termine correctamente:

```powershell
if (!(Test-Path infra/bootstrap/backend.tf)) {
    Copy-Item infra/bootstrap/backend.tf.example infra/bootstrap/backend.tf
}
terraform "-chdir=infra/bootstrap" init -migrate-state
```

Aceptar la copia del estado al backend S3 cuando Terraform lo solicite. Verificar:

```powershell
terraform "-chdir=infra/bootstrap" plan
```

Debe indicar que no hay cambios. Subir backend.tf y .terraform.lock.hcl a Git.
No subir archivos terraform.tfstate, copias de estado ni planes. Tras la migración,
los demás colaboradores clonan el código y ejecutan init; no repiten el bootstrap
desde cero ni vuelven a copiar la plantilla.

## 4. Preparar los repositorios ECR

Este bloque describe la fase inicial de ECR ya realizada. La carpeta DEV incluye
ahora también EC2 y su red: antes de generar un nuevo plan, completar las variables
del apartado 6. Revisar siempre el plan completo; no asumir que solo creará ECR.

```powershell
terraform "-chdir=infra/environments/dev" init
terraform "-chdir=infra/environments/dev" validate
terraform "-chdir=infra/environments/dev" plan "-out=dev.tfplan"
```

En la fase inicial añadía dos repositorios y dos políticas. Con la configuración
actual, una instalación nueva incluye también los recursos del apartado 6; el
entorno ya desplegado debe conservarlos. Después de revisar el plan concreto:

```powershell
terraform "-chdir=infra/environments/dev" apply "dev.tfplan"
terraform "-chdir=infra/environments/dev" output repository_urls
```

Repositorios: homologaciones-dev/frontend y homologaciones-dev/backend. Las etiquetas
son inmutables: publicar cada versión con una etiqueta nueva, preferiblemente el
commit Git. No utilizar latest como etiqueta que se sobrescribe. Las imágenes sin
etiqueta caducan a los siete días; las etiquetadas requieren revisar su retención
para controlar el almacenamiento. El escaneo básico no bloquea el despliegue por sí solo.

Conservar en Git los dos archivos .terraform.lock.hcl generados por init para fijar
la versión del proveedor. No ejecutar apply simultáneamente entre colaboradores.
El bloqueo del backend protege frente a escrituras concurrentes; no desactivarlo.

## 5. Autenticación de Docker en Windows y uso de ECR

En este piloto, Docker Desktop falló al guardar la contraseña larga de ECR mediante
el gestor `desktop`. Se configuró Amazon ECR Credential Helper para ese registro.
Instalar el ejecutable Windows AMD64 desde las
[descargas oficiales](https://github.com/awslabs/amazon-ecr-credential-helper/releases),
con nombre `docker-credential-ecr-login.exe`, en una carpeta del Path del usuario.

En `%USERPROFILE%\.docker\config.json`, conservar la configuración existente y
añadir o ampliar la propiedad `credHelpers` con esta entrada:

```json
{
  "credHelpers": {
    "086358667619.dkr.ecr.eu-west-1.amazonaws.com": "ecr-login"
  }
}
```

El fragmento no sustituye el resto del archivo. Con el perfil auxiliar configurado
en el apartado 1, seleccionar la sesión y verificar la cuenta:

```powershell
$env:AWS_PROFILE = 'homologaciones-dev-terraform'
aws sts get-caller-identity
Get-Command docker-credential-ecr-login
```

El helper obtiene las credenciales durante push/pull sin ejecutar docker login.
No compartir contraseñas ni imprimir los tokens. Esta configuración es local al
ordenador; no se copia a las imágenes ni se utiliza como identidad de la EC2.

La versión `piloto-20261105-081821` está publicada en ambos repositorios. Para
seleccionarla y descargarla, seguir el apartado de ECR de la
[guía Docker](../docs/BASE_DESPLIEGUE.md#usar-las-imágenes-publicadas-en-ecr).

### Publicar una nueva versión (PowerShell local)

Con Docker Desktop abierto y la cuenta DEV verificada, construir y probar primero
las imágenes locales. Para conservar el flujo de pruebas, dejar vacías las variables
`BACKEND_IMAGE` y `FRONTEND_IMAGE` en el entorno local durante la construcción.
Después de validarlas, etiquetar y publicar con una versión nueva:

```powershell
$registroEcr = '086358667619.dkr.ecr.eu-west-1.amazonaws.com'
$versionImagen = "piloto-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
docker tag homologaciones-dev-backend:latest "${registroEcr}/homologaciones-dev/backend:${versionImagen}"
docker tag homologaciones-dev-frontend:latest "${registroEcr}/homologaciones-dev/frontend:${versionImagen}"
docker push "${registroEcr}/homologaciones-dev/backend:${versionImagen}"
# Continuar solo si el primer push termina correctamente.
docker push "${registroEcr}/homologaciones-dev/frontend:${versionImagen}"
$versionImagen
```

La etiqueta con fecha identifica la prueba manual; para automatizar se utilizará
una versión ligada al commit y se promocionará la imagen validada. Verificar ambas:

```powershell
aws ecr describe-images --repository-name homologaciones-dev/backend --image-ids "imageTag=$versionImagen" --region eu-west-1 --profile homologaciones-dev --query 'imageDetails[0].{Version:imageTags,Digest:imageDigest}' --output json
aws ecr describe-images --repository-name homologaciones-dev/frontend --image-ids "imageTag=$versionImagen" --region eu-west-1 --profile homologaciones-dev --query 'imageDetails[0].{Version:imageTags,Digest:imageDigest}' --output json
```

## 6. Preparar el host EC2 de DEV

### Qué se creará

- VPC y subred pública propias, con salida a Internet mediante Internet Gateway.
  No se añade NAT Gateway, balanceador ni Elastic IP.
- Security Group: SSH desde una sola IPv4 /32. Los puertos 8000/8501 permanecen
  cerrados al exterior. HTTP/HTTPS se habilitarán después mediante
  `enable_public_web = true`, cuando Caddy y el dominio estén preparados.
- EC2 `t3.medium` con Ubuntu Server 24.04 LTS amd64 de Canonical. AMI fijada
  explícitamente en las variables, IMDSv2 obligatorio y CPU Standard para evitar
  cargos por créditos Unlimited; puede limitar rendimiento al agotar créditos.
- 20 GiB gp3 cifrados para Ubuntu, Docker y sus imágenes; 10 GiB gp3 cifrados en
  otro volumen para configuración, ChromaDB y outputs: 30 GiB totales.
- Rol `homologaciones-dev-ec2`, con descarga de imágenes limitada a los dos
  repositorios ECR. No concede escritura, administración ni acceso al estado S3.
- Preparación inicial automática: Docker, Compose, AWS CLI y montaje del disco
  en `/srv/homologaciones`. No se incluyen claves ni corpus en user_data.

La instancia y el volumen de datos tienen `prevent_destroy`: Terraform rechazará
eliminaciones y sustituciones hasta revisar y retirar esa protección del código.
Esto no impide una eliminación manual desde AWS ni sustituye las copias. El disco
de sistema se elimina al terminar la instancia; el de datos se gestiona por separado.
Las imágenes y los volúmenes Docker de certificados Caddy seguirán en el disco de
sistema: respaldar también esos certificados antes de sustituir la máquina.

### Clave SSH y variables (PowerShell local)

1. Entrar con la identidad individual en DEV, seleccionar Irlanda y abrir
   EC2 → Network & Security → Key pairs → Create key pair.
2. Nombre sugerido: `homologaciones-dev`; tipo RSA, formato `.pem`. Guardar la
   descarga fuera del repositorio. Una clave de la cuenta personal del piloto no
   existe automáticamente en DEV. El `.pem` no se introduce en Terraform.
3. Consultar tu IPv4 pública actual y anotarla como `TU_IP/32`. Debe ser la IP de
   tu conexión, no la de una EC2. Se puede consultar buscando «cuál es mi IP» en el
   navegador. Si cambia, actualizar la variable y aplicar el cambio de regla.
4. Obtener la AMI actual de Ubuntu 24.04 desde el parámetro público de Canonical:

```powershell
aws ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id --region eu-west-1 --profile homologaciones-dev --query Parameter.Value --output text
```

Copiar el identificador obtenido al archivo de variables; no ejecutar consultas
automáticas de «latest» en cada plan. Así una nueva publicación de Ubuntu no
provoca reemplazar la EC2 sin haber cambiado su configuración explícitamente.

```powershell
if (!(Test-Path infra/environments/dev/terraform.tfvars)) {
    Copy-Item infra/environments/dev/terraform.tfvars.example infra/environments/dev/terraform.tfvars
}
```

Editar `terraform.tfvars` con el nombre de clave, IPv4 /32 y AMI reales. Dejar
`enable_public_web = false`. Esta configuración local está excluida de Git. Los
socios deben coordinar estos valores: actualmente se permite un solo origen SSH.
No utilizar los valores ficticios de la plantilla como configuración real.

### Revisar el plan y crear la máquina

Con la sesión DEV y el perfil auxiliar activos:

```powershell
terraform "-chdir=infra/environments/dev" init
terraform "-chdir=infra/environments/dev" validate
terraform "-chdir=infra/environments/dev" plan "-out=compute.tfplan"
```

En el entorno existente, el plan debe conservar los repositorios y sus políticas,
y añadir 14 recursos: red (5), Security Group y reglas (3), rol/política/perfil (3),
EC2 (1), volumen de datos (1) y su conexión (1). No ejecutar si propone borrar
recursos o modificar los repositorios sin una causa revisada.

Después de revisar el plan:

```powershell
terraform "-chdir=infra/environments/dev" apply "compute.tfplan"
terraform "-chdir=infra/environments/dev" output
```

El cómputo empieza a facturarse al arrancar. Los discos conservados siguen
facturándose al detener la EC2. No se reserva IP: puede cambiar al parar/arrancar.

### Verificar la preparación (Ubuntu remoto)

Usar la IP de los outputs y la clave descargada. En PowerShell:

```powershell
$claveDev = 'C:\ruta-privada\homologaciones-dev.pem'
ssh -i "$claveDev" ubuntu@IP_PUBLICA
```

Verificar la huella del host. Si Windows rechaza los permisos del PEM, consultar
el apartado SSH de [la guía EC2](../docs/DESPLIEGUE_EC2.md#4-conectar-por-ssh).
Terraform puede terminar antes de completar la instalación inicial. En Ubuntu:

```bash
sudo cloud-init status --wait
sudo test -f /var/lib/cloud/instance/homologaciones-host-ready && echo 'Host preparado'
sudo docker --version
sudo docker compose version
aws --version
findmnt /srv/homologaciones
df -h / /srv/homologaciones
aws sts get-caller-identity --region eu-west-1
```

La identidad del host debe ser `assumed-role/homologaciones-dev-ec2/...` de DEV.
No ejecutar aws login, copiar perfiles personales ni usar el helper Windows allí.
Para descargar desde Ubuntu se usará `aws ecr get-login-password` con ese rol.
El acceso a metadatos se limita al host; los contenedores no necesitan ese rol.

Si falla la preparación, revisar `sudo tail -n 100 /var/log/cloud-init-output.log`.
El script solo formatea el volumen nuevo identificado por su serial EBS; conserva
un ext4 existente y falla ante formatos inesperados. No formatear manualmente ni
arrancar servicios hasta confirmar que `/srv/homologaciones` es el disco montado.
Una marca de preparación no valida la aplicación ni sustituye las pruebas funcionales.

Las rutas previstas del servidor son:

| Contenido | Ruta |
|---|---|
| Compose y `.env.dev` | `/srv/homologaciones/app/` |
| Índice completo | `/srv/homologaciones/chroma_db/` (se copiará, no se crea vacío) |
| Word generados | `/srv/homologaciones/outputs/` |
| Configuración Caddy | `/srv/homologaciones/caddy/` |

En el entorno remoto, ajustar las variables de rutas a esos valores absolutos;
no copiar literalmente las rutas Windows ni las rutas relativas del entorno local.

## 7. Transferencia inicial y arranque privado

**Solo para la instalación inicial.** No repetir la extracción sobre un índice
activo ni copiar los outputs locales a DEV. Sustituir `IP_PUBLICA` por la IP actual
de Terraform y conservar el PEM fuera del repositorio.

En PowerShell local, desde la raíz del proyecto, detener los contenedores que usan
el índice y transferir una copia consistente:

```powershell
$claveDev = 'C:\ruta-privada\homologaciones-dev.pem'
docker compose --env-file .env.dev -f compose.ec2.yml stop
tar -czf "$env:TEMP\homologaciones-chroma-dev.tar.gz" -C data/dev chroma_db
scp -i "$claveDev" "$env:TEMP\homologaciones-chroma-dev.tar.gz" ubuntu@IP_PUBLICA:/home/ubuntu/
scp -i "$claveDev" compose.ec2.yml compose.public.yml .env.example ubuntu@IP_PUBLICA:/srv/homologaciones/app/
```

En Ubuntu remoto, comprobar el montaje antes de extraer. Si existe ya la carpeta
del índice, no sobrescribirla: revisar su contenido y el procedimiento de actualización.

```bash
mountpoint /srv/homologaciones
sudo test ! -e /srv/homologaciones/chroma_db && sudo tar -xzf /home/ubuntu/homologaciones-chroma-dev.tar.gz -C /srv/homologaciones
sudo chown -R 1000:1000 /srv/homologaciones/chroma_db
ls -lh /srv/homologaciones/chroma_db/chroma.sqlite3
cd /srv/homologaciones/app
test -e .env.dev || cp .env.example .env.dev
chmod 600 .env.dev
nano .env.dev
```

Conservar la carpeta completa del índice, incluidos sus subdirectorios vectoriales.
El `.env.dev` remoto no es el mismo archivo que el local: añadir la clave OpenAI de
forma privada y ajustar rutas e imágenes. No copiar perfiles CLI, PEM ni tokens.

```dotenv
APP_ENV_FILE=.env.dev
COMPOSE_PROJECT_NAME=homologaciones-dev
CHROMA_HOST_PATH=/srv/homologaciones/chroma_db
OUTPUT_HOST_PATH=/srv/homologaciones/outputs
CADDY_CONFIG_PATH=/srv/homologaciones/caddy
FRONTEND_PORT=8501
BACKEND_IMAGE=086358667619.dkr.ecr.eu-west-1.amazonaws.com/homologaciones-dev/backend:piloto-20261105-081821
FRONTEND_IMAGE=086358667619.dkr.ecr.eu-west-1.amazonaws.com/homologaciones-dev/frontend:piloto-20261105-081821
```

Completar `OPENAI_API_KEY` con una clave válida de OpenAI (no de LangSmith), mantener
el modelo de embeddings usado al indexar y dejar las trazas desactivadas si no se
utilizan. Guardar en nano con Ctrl+O, Enter; salir con Ctrl+X. Dejar inicialmente
`PUBLIC_DOMAIN` vacío. Las claves no se incorporan al archivo de ejemplo ni al estado.

En Ubuntu, el rol del host autentica la descarga; no se necesita el helper Windows:

```bash
sudo docker compose --env-file .env.dev -f compose.ec2.yml config --quiet
aws ecr get-login-password --region eu-west-1 | sudo docker login --username AWS --password-stdin 086358667619.dkr.ecr.eu-west-1.amazonaws.com
sudo docker compose --env-file .env.dev -f compose.ec2.yml pull backend frontend
# Continuar solo si la descarga termina correctamente.
sudo docker compose --env-file .env.dev -f compose.ec2.yml up -d --no-build --pull never
sudo docker compose --env-file .env.dev -f compose.ec2.yml ps
```

`pull` solo descarga. Es `up` quien crea y arranca los contenedores. Esperar a
`healthy` en ambos. En otra terminal PowerShell local:

```powershell
ssh -i "$claveDev" -N -L 8502:127.0.0.1:8501 ubuntu@IP_PUBLICA
```

Mantener el túnel abierto y visitar http://localhost:8502. El puerto 8502 es local
al PC; el destino 8501 pertenece a EC2. Probar chatbot y generación/descarga de Word.
No abrir 8501 en el Security Group. Esta prueba no utiliza el Streamlit local.

## 8. Publicación con DuckDNS, HTTPS y contraseña

### Dominio y configuración (Ubuntu remoto y navegador)

En DuckDNS, crear o reutilizar el subdominio y apuntar su IPv4 a la IP de EC2.
DEV utiliza `upgradewith-ai.duckdns.org`. IPv6 queda vacío porque no se ha configurado.
No compartir el token de DuckDNS. Comprobar en Ubuntu:

```bash
getent ahostsv4 upgradewith-ai.duckdns.org
```

Debe devolver la IPv4 pública actual del servidor. En PowerShell local, copiar Caddy:

```powershell
scp -i "$claveDev" deploy/caddy/Caddyfile ubuntu@IP_PUBLICA:/srv/homologaciones/caddy/
```

En Ubuntu, generar el hash y crear el archivo de usuarios:

```bash
sudo docker run --rm -it caddy:2-alpine caddy hash-password
nano /srv/homologaciones/caddy/users.caddy
```

Introducir una línea `piloto HASH_BCRYPT_COMPLETO`. El comando solicita la contraseña
sin mostrar caracteres. Guardar el hash completo, no la contraseña en claro, y no
compartir ese archivo. Añadir al `.env.dev` remoto:

```dotenv
PUBLIC_DOMAIN=upgradewith-ai.duckdns.org
```

Desde `/srv/homologaciones/app`:

```bash
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml config --quiet
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Se espera `Valid configuration`. El aviso de formato del Caddyfile no impide
arrancar. La validación no publica el servicio ni obtiene aún el certificado.

### Abrir la web mediante Terraform (PowerShell local)

Cambiar en `infra/environments/dev/terraform.tfvars`:

```hcl
enable_public_web = true
```

```powershell
$env:AWS_PROFILE = 'homologaciones-dev-terraform'
terraform "-chdir=infra/environments/dev" plan "-out=public-web.tfplan"
```

En el entorno privado ya creado, se esperan únicamente dos altas: reglas HTTP 80
y HTTPS 443 desde `0.0.0.0/0`. Sin modificaciones ni eliminaciones. Revisar y aplicar:

```powershell
terraform "-chdir=infra/environments/dev" apply "public-web.tfplan"
```

Esta variable ya está en `true` en el despliegue publicado: al incorporarse un socio,
conservar ese valor para no cerrar la web inadvertidamente al aplicar la plantilla.

### Arrancar y comprobar (Ubuntu remoto)

```bash
cd /srv/homologaciones/app
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml up -d --no-build --pull never
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml ps
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml logs --tail=60 caddy
curl -I https://upgradewith-ai.duckdns.org
```

Si falta la imagen de Caddy, descargarla con ambos Compose mediante `pull caddy`
y repetir el arranque. Sin credenciales se espera `401 Unauthorized` con certificado
válido. No usar `curl -k`: ocultaría errores del certificado. Caddy obtiene y renueva
HTTPS automáticamente y redirige HTTP a HTTPS; necesita DNS, puertos accesibles y
sus volúmenes persistentes. La primera emisión puede tardar unos instantes.

Abrir https://upgradewith-ai.duckdns.org en privado y desde un móvil sin Wi-Fi:
debe pedir usuario `piloto` y la contraseña original. Probar chatbot y Word. El
túnel SSH ya no es necesario para usar la web. Compartir URL y contraseña por un
canal privado; nadie necesita recibir el PEM ni la clave de OpenAI.

## 9. Operación y actualizaciones

### Retomar después de cerrar el ordenador

La aplicación continúa en AWS aunque se cierre el PC o SSH. En PowerShell local,
renovar acceso solo si hace falta y seleccionar el perfil:

```powershell
aws login --profile homologaciones-dev
$env:AWS_PROFILE = 'homologaciones-dev-terraform'
aws sts get-caller-identity
```

Debe devolver DEV, no Identity Delegated Admin. El perfil con nombre «dev» no impide
seleccionar una cuenta equivocada en el navegador. No repetir bootstrap, migración
ni creación de recursos. Un socio clona el código, obtiene los valores actuales
de variables de forma coordinada y ejecuta `init` y `plan`, usando el estado S3.

### Actualizar código o configuración

Publicar y verificar imágenes nuevas según el apartado 5. Cambiar las dos URI del
`.env.dev` remoto a la versión validada, conservando rutas, secretos y datos. Con
la sesión SSH en Ubuntu, desde `/srv/homologaciones/app`:

```bash
aws ecr get-login-password --region eu-west-1 | sudo docker login --username AWS --password-stdin 086358667619.dkr.ecr.eu-west-1.amazonaws.com
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml pull backend frontend
# Continuar solo si ambas descargas terminan correctamente.
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml up -d --no-build --pull never
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml ps
```

No reconstruir en el servidor ni reenviar el índice para un cambio de código.
La recreación puede interrumpir sesiones y perder revisiones en memoria. Si cambia
el Compose o el Caddyfile, transferir únicamente esos archivos y validar antes.
Para una clave o variable nueva, `up` recrea los servicios afectados; `restart`
no recarga el entorno Docker. Se puede forzar la recreación añadiendo
`--force-recreate` al comando `up`, con ambas configuraciones.

Para volver a una versión anterior, restaurar sus URI y repetir descarga y arranque,
siempre que sea compatible con los datos. No revierte automáticamente cambios de datos.
Los cambios de red/máquina/permisos siguen el flujo separado de Terraform plan/apply.
La actualización de Chroma requiere parar servicios, respaldar y sustituir el índice
completo validado y sus JSON/grafo compatibles; no copiar sobre el índice activo.

### Pausa, costes y vuelta al servicio

Para pausar, esperar a que terminen las generaciones y usar EC2 → Instance state →
Stop instance. Cerrar el navegador, SSH o parar contenedores no detiene la máquina.
Parar EC2 evita el cómputo mientras está parada, pero siguen los cargos por ambos
EBS, ECR, S3 y cualquier copia conservada. Una Elastic IP reservada, si se añadiese
en el futuro, tendría su propio coste. Los avisos de presupuesto no apagan recursos.

Al arrancar de nuevo:

1. Consultar la IPv4 actual en EC2 y actualizar DuckDNS si ha cambiado.
2. Si cambió la IP del administrador, actualizar `admin_ipv4_cidr` y revisar/aplicar
   el cambio con Terraform antes de reconectar por SSH.
3. Comprobar montaje del disco y los tres servicios con ambos Compose; ejecutar
   `up -d --no-build --pull never` si quedaron detenidos manualmente.
4. Comprobar HTTPS, contraseña, chatbot y documentos.

No utilizar Terminate como pausa. `prevent_destroy` protege frente a Terraform,
no frente a la eliminación desde la consola. No usar `down -v`: elimina los volúmenes
Docker de Caddy. Para eliminar todos los costes hace falta planificar la retirada
de todos los recursos y copias; stop no equivale a coste cero.

### Persistencia y copias

| Información | Ubicación y comportamiento |
|---|---|
| ChromaDB, outputs, entorno y configuración de Caddy | Disco de datos separado en `/srv/homologaciones` |
| Imágenes locales y certificados Caddy | Disco de sistema; certificados en volúmenes Docker |
| Estado Terraform | S3 privado con versiones y bloqueo |
| Historial/checkpoints en memoria | Se pierden al reiniciar o recrear servicios |

No hay copias automáticas configuradas. Para una copia consistente, detener los
servicios con ambos Compose, tomar snapshots de los discos de sistema y datos y
esperar a que terminen antes de reanudar. Las copias contienen secretos y deben
permanecer privadas; definir retención y probar restauración en un entorno aislado.
El versionado del estado de Terraform no respalda ChromaDB ni los documentos.

## 10. Diagnóstico del despliegue realizado

En Ubuntu, desde `/srv/homologaciones/app`:

```bash
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml ps
sudo docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml logs --tail=80 backend frontend caddy
findmnt /srv/homologaciones
df -h
```

| Síntoma | Comprobación / solución |
|---|---|
| PowerShell no encuentra Terraform/helper | Revisar Path del usuario o recuperar rutas en la sesión |
| CLI entra en una cuenta central | Repetir login seleccionando la cuenta DEV y verificar STS |
| Login ECR da 400 en PowerShell o `The stub received bad data` | Utilizar el helper específico de ECR según apartado 5, sin borrar la configuración Docker |
| SSH rechaza el PEM por permisos | Conceder lectura al usuario, retirar herencia y solo las entradas ajenas que señale SSH; ver guía histórica de SSH |
| Túnel SSH: `connect failed: Connection refused` | SSH funciona, pero frontend no escucha: comprobar que se ejecutó `up` después de `pull` y revisar `ps`/logs |
| Error 500 en `/consulta` | Revisar respuesta y logs; se detectó una clave LangSmith puesta como OPENAI_API_KEY. Corregir el entorno y recrear los contenedores |
| `Valid configuration` pero no abre HTTPS | Aún falta arrancar Caddy, o revisar DNS y reglas 80/443 |
| HTTP 401 sin credenciales | Resultado esperado de la protección de Caddy |
| No se guardan Word / error de Chroma | Comprobar montaje, rutas, índice completo y permisos UID/GID 1000 |

No imprimir `.env.dev`, contraseñas ni tokens en diagnósticos compartidos. Si una
clave API se expone, revocarla en el proveedor, sustituirla en los entornos y recrear
los contenedores afectados; el ejemplo de documentación nunca debe contenerla.

## 11. Registro y próximos pasos

Despliegue DEV realizado el **5 de noviembre de 2026**, validado por el equipo.
Estos identificadores son una referencia del despliegue; no son valores para
recrear recursos manualmente ni sustituyen los outputs y el estado de Terraform.

| Elemento | Valor registrado |
|---|---|
| Región / cuenta | `eu-west-1` / `086358667619` |
| EC2 | `i-0cfac93db6ece709a` |
| IPv4 en esta fecha (puede cambiar) | `54.74.157.166` |
| Volumen de datos | `vol-0d727ef2ef000cca8` |
| Rol EC2 | `homologaciones-dev-ec2` |
| Versión de ambas imágenes | `piloto-20261105-081821` |
| Backend digest | `sha256:67b70e8800bdedc9b48fea698bc3c26c034f1b40b0b68ec45bd6c9ec254393ba` |
| Frontend digest | `sha256:fe173e0a80dae3145da180e9ea1ddba8f2e27356aff023d1a5222bd512a15554` |
| URL | https://upgradewith-ai.duckdns.org |

Comprobado: estado compartido, publicación y descarga ECR, cloud-init terminado,
disco montado, rol EC2 correcto, frontend/backend saludables, acceso privado con
túnel y acceso público mediante Caddy con HTTPS y contraseña. Se probaron chatbot
y generación de Word desde las imágenes publicadas y el acceso al entorno remoto.

Pendientes: PROD, automatización GitHub Actions/OIDC, actualización automática de
DuckDNS, copias automáticas y prueba de restauración, usuarios de aplicación y
aislamiento de expedientes, persistencia de conversaciones/revisiones y Bedrock.
El piloto mantiene una contraseña compartida; no es aún una plataforma multiusuario
con aislamiento de datos ni alta disponibilidad.

Referencias: [backend S3](https://developer.hashicorp.com/terraform/language/backend/s3)
y [repositorios ECR](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_repository).
