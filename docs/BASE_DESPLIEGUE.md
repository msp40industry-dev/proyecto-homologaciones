# Base Docker y configuración de entornos

Esta fase prepara contenedores. No crea infraestructura AWS, usuarios de
aplicación, persistencia de expedientes ni integración con Bedrock.

## Imágenes

Un único `Dockerfile` contiene los destinos `backend` y `frontend`, con una base
común Python 3.11 + Node.js 24. Ambos necesitan Node para generar Word.
`npm ci` usa `package-lock.json`. Las herramientas de compilación Python quedan
en una etapa de construcción, fuera de la imagen final.

La aplicación se ejecuta como usuario `app` (UID/GID 1000). ChromaDB y outputs
deben ser escribibles por ese usuario. No usar permisos 777.

Las versiones principales de las imágenes están seleccionadas, pero sus etiquetas
siguen recibiendo actualizaciones y las dependencias Python transitivas no están
bloqueadas completamente. Esto no garantiza builds idénticos byte a byte. La
publicación posterior en ECR deberá identificar cada imagen por versión/digest y
promocionar la misma imagen validada de DEV a PROD.

## Elegir configuración

La plantilla única es `.env.example`. Sus valores Docker mantienen el modo con
`.env`. Para entornos separados, copiarla a `.env.dev` o `.env.prod`, ajustar
los valores de la tabla siguiente y completar los secretos. No subir los archivos
reales a Git. Si ya existe la configuración del entorno, conservarla: no sobrescribirla
con la plantilla.

En PowerShell local, desde la raíz:

```powershell
if (!(Test-Path .env.dev)) { Copy-Item .env.example .env.dev }
```

En Ubuntu remoto:

```bash
test -e .env.dev || cp .env.example .env.dev
chmod 600 .env.dev
nano .env.dev
```

Antes de arrancar, ajustar estas variables en la copia elegida:

| Variable | DEV (`.env.dev`) | PROD (`.env.prod`) |
|---|---|---|
| `APP_ENV_FILE` | `.env.dev` | `.env.prod` |
| `COMPOSE_PROJECT_NAME` | `homologaciones-dev` | `homologaciones-prod` |
| `CHROMA_HOST_PATH` | `./data/dev/chroma_db` | `./data/prod/chroma_db` |
| `OUTPUT_HOST_PATH` | `./data/dev/outputs` | `./data/prod/outputs` |
| `CADDY_CONFIG_PATH` | `./data/dev/caddy` | `./data/prod/caddy` |
| `FRONTEND_PORT` | `8501` | `8502` |
| `LANGCHAIN_PROJECT` | `homologaciones-dev` | `homologaciones-prod` |

`OPENAI_API_KEY` debe contener una clave válida de OpenAI. `PUBLIC_DOMAIN` puede
quedar vacío en las pruebas privadas; para publicar, usar el dominio del entorno.
Para PROD, los comandos siguientes se adaptan usando `.env.prod` y `data/prod`.

El fichero seleccionado tiene dos usos:

- `--env-file .env.dev`: proporciona a Compose las variables para interpolar
  rutas, puerto y nombre del proyecto Docker.
- `APP_ENV_FILE=.env.dev`: indica qué archivo carga Compose dentro de frontend
  y backend. No se copia a la imagen.

Usar siempre el mismo `--env-file` con `config`, `up`, `ps`, `logs`, `exec` y
`stop`. En el despliegue público, también usar los dos archivos Compose.

| Variable | Función |
|---|---|
| `COMPOSE_PROJECT_NAME` | Separa contenedores, red y volúmenes Docker por entorno |
| `CHROMA_HOST_PATH` | Carpeta del índice en el host |
| `OUTPUT_HOST_PATH` | Carpeta de Word en el host |
| `CADDY_CONFIG_PATH` | Carpeta con `Caddyfile` y `users.caddy` |
| `FRONTEND_PORT` | Puerto local del túnel; Streamlit usa 8501 dentro del contenedor |
| `PUBLIC_DOMAIN` | Dominio del entorno; requerido únicamente con Caddy |

La plantilla no incorpora claves reales ni cambia el modelo de embeddings.
El índice y el modelo de consulta deben coincidir.

## Datos y permisos (Ubuntu remoto)

Para un DEV nuevo, sin servicios activos, desde la raíz del proyecto:

```bash
mkdir -p data/dev/outputs data/dev/caddy
cp -a scripts_index/chroma_db data/dev/chroma_db
cp deploy/caddy/Caddyfile data/dev/caddy/Caddyfile
```

Copiar el índice con los procesos que lo utilizan detenidos. No copiar encima de
un índice activo ni crear solo un `chroma.sqlite3` vacío. Para PROD, utilizar un
corpus validado y sus propias carpetas `data/prod`; no copiar expedientes DEV.

Comprobar propietario y permisos:

```bash
id
ls -ldn data/dev/chroma_db data/dev/outputs
```

En una EC2 Ubuntu nueva, `ubuntu` suele tener UID/GID 1000. Si los datos tienen
otro propietario, ajustar únicamente las dos carpetas del entorno, tras confirmar
sus rutas absolutas con `realpath`. Por ejemplo, para la instalación documentada:

```bash
sudo chown -R 1000:1000 /home/ubuntu/proyecto-homologaciones/data/dev/chroma_db /home/ubuntu/proyecto-homologaciones/data/dev/outputs
```

El montaje oculta los permisos creados dentro de la imagen: reconstruir no repara
permisos del host. `compose.ec2.yml` falla si faltan las carpetas de datos en lugar
de crear accidentalmente un índice vacío.

Si se conserva la configuración antigua `.env`, preparar `outputs` y comprobar
también los permisos de `scripts_index/chroma_db` antes de recrear contenedores.

## Validar y arrancar DEV

Con Docker disponible, desde la raíz (Ubuntu, añadir `sudo` si es necesario):

```bash
docker compose --env-file .env.dev -f compose.ec2.yml config --quiet
docker compose --env-file .env.dev -f compose.ec2.yml build
docker compose --env-file .env.dev -f compose.ec2.yml up -d
docker compose --env-file .env.dev -f compose.ec2.yml ps
docker compose --env-file .env.dev -f compose.ec2.yml exec backend node --version
docker compose --env-file .env.dev -f compose.ec2.yml exec frontend python -c "import requests; r=requests.get('http://backend:8000/health', timeout=10); print(r.status_code); r.raise_for_status()"
```

Backend debe pasar su comprobación de salud antes de arrancar frontend. Caddy
espera a la salud de Streamlit. Estas comprobaciones no hacen llamadas a IA ni
validan el corpus o la calidad de generación. Si un contenedor queda `unhealthy`,
consultar logs; Docker no reinicia automáticamente por ese estado por sí solo.

Validar además Node.js y `docx` en ambos destinos:

```bash
docker compose --env-file .env.dev -f compose.ec2.yml exec backend node -e "const {Document,Packer,Paragraph}=require('docx'); Packer.toBuffer(new Document({sections:[{children:[new Paragraph('Prueba Docker')]}]})).then(b=>console.log('DOCX bytes:',b.length)).catch(e=>{console.error(e);process.exit(1)})"
docker compose --env-file .env.dev -f compose.ec2.yml exec frontend node -e "require('docx'); console.log('docx disponible')"
```

Abrir túnel SSH al puerto local elegido y probar consulta RAG y generación Word
completa. Los comandos anteriores no sustituyen esa prueba funcional.

## Publicación y operación

Generar `users.caddy` en la carpeta indicada por `CADDY_CONFIG_PATH`, manteniendo
el hash fuera del repositorio. Preparar DNS y reglas 80/443 como indica
[DESPLIEGUE_EC2.md](DESPLIEGUE_EC2.md).

```bash
docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml config --quiet
docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml up -d --build
docker compose --env-file .env.dev -f compose.ec2.yml -f compose.public.yml ps
```

No ejecutar DEV y PROD públicos simultáneamente en una misma máquina: ambos
publican 80/443. El destino previsto son cuentas/servidores separados. Separar
Compose no es un control de permisos entre cuentas AWS; eso llegará con Terraform.

## Compatibilidad y siguientes fases

La preparación de S3 para el estado compartido y ECR se documenta en
[infra/README.md](../infra/README.md).

- Se sustituyen `Dockerfile.frontend` y `Dockerfile.backend` por los destinos del
  `Dockerfile` común. Actualizar cualquier script externo que los referencie.
- La imagen solo incluye el código necesario, JSON y grafo; los parsers y scripts
  de indexación se ejecutan fuera de la imagen de aplicación.
- No copiar el paquete inicial sobre un servidor activo: puede sobrescribir datos.
- Cambiar de nombre de proyecto Compose crea otros servicios/volúmenes. Detener
  los anteriores con su configuración antes de migrar y conservar los certificados;
  no usar `down -v`.
- No se cambia la API, la marca de agua Word, el índice ni el estado de LangGraph.
- Terraform, ECR, CI, Bedrock, usuarios y persistencia de expedientes se abordarán
  en fases separadas.
