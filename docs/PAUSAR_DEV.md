# Pausar y reanudar DEV con bajo coste

## Opción habitual: detener la máquina y conservar los datos

El script `deploy/dev.ps1` permite parar y arrancar la EC2 sin borrar discos,
contenedores, configuración ni imágenes. Ejecutar en PowerShell local, desde
la raíz del repositorio, con AWS CLI disponible y acceso al perfil DEV:

```powershell
aws login --profile homologaciones-dev
.\deploy\dev.ps1 status
.\deploy\dev.ps1 pause
```

`pause` solicita la parada normal de Ubuntu y espera al estado `stopped`. Esperar a
que terminen las generaciones antes de ejecutarlo: las revisiones y conversaciones
en memoria se pierden al apagar. No termina ni elimina la instancia. No hace falta
parar Docker a mano; así `restart: unless-stopped` permite recuperar los contenedores
cuando vuelva a arrancar el sistema.

La pausa apaga la EC2 completa: frontend, backend y Caddy dejan de ejecutarse y la
URL no estará disponible. No elimina datos, certificados ni configuración. Los
discos EBS, repositorios ECR, estado S3 y recursos de red se mantienen.
Los nombres anteriores `stop` y `start` siguen funcionando como alias de `pause`
y `resume`. Archive/restore no forman parte de este script.

Para reanudar:

```powershell
.\deploy\dev.ps1 resume
```

Espera a que EC2 esté ejecutándose y pase sus comprobaciones de sistema; muestra
la nueva IP. Esto no garantiza que los contenedores ni OpenAI estén saludables.
Actualizar DuckDNS si cambió la dirección y comprobar la URL pública y la aplicación.
Si los contenedores se habían detenido manualmente, arrancarlos por SSH con ambos
Compose, según [la guía de operación](../infra/README.md#9-operación-y-actualizaciones).
Si cambió la IP de tu conexión, actualizar también la regla SSH mediante Terraform.

Si PowerShell bloquea la ejecución de scripts, permitirlos únicamente en esta
terminal, después de revisar el script del repositorio:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Esto no cambia la política permanente de Windows. Si el equipo aplica una política
corporativa que lo impide, utilizar las operaciones Stop/Start de la consola EC2.

## Reanudar y actualizar DuckDNS con un comando

La IP pública se asigna automáticamente y puede cambiar al arrancar. Para que el
script la actualice en `upgradewith-ai.duckdns.org`, cargar el token de DuckDNS en
la terminal. El token se obtiene en tu cuenta DuckDNS; no es la contraseña de Caddy
ni una clave AWS. Introducirlo sin guardarlo en el historial de comandos:

```powershell
$tokenDnsSeguro = Read-Host 'Token de DuckDNS' -AsSecureString
$env:DUCKDNS_TOKEN = [System.Net.NetworkCredential]::new('', $tokenDnsSeguro).Password
.\deploy\dev.ps1 resume -UpdateDns
```

El script no imprime el token ni lo escribe en Git o en el estado Terraform. Se
envía por HTTPS a DuckDNS. La variable permanece en la memoria de esa terminal;
eliminarla al terminar:

```powershell
Remove-Item Env:DUCKDNS_TOKEN -ErrorAction SilentlyContinue
$tokenDnsSeguro = $null
```

Si el token no está cargado, `resume -UpdateDns` falla antes de arrancar. Si falla
la actualización de DNS después del arranque, la máquina permanece encendida:
actualizar la IP manualmente o detenerla si ya no se va a usar. No interpretar
un error de DNS como una parada de la EC2. La propagación DNS puede tardar.

## Qué queda facturándose mientras está parada

| Recurso actual | Al parar EC2 |
|---|---|
| Cómputo `t3.medium` | Deja de facturarse durante la parada |
| IPv4 pública automática | Se libera; no se conserva una Elastic IP |
| EBS sistema 20 GiB + datos 10 GiB | Se conservan y siguen facturándose |
| ECR | Las imágenes almacenadas siguen facturándose |
| S3 del estado | Conserva estado y versiones; almacenamiento y peticiones |
| VPC, subred, Security Group, rutas, Internet Gateway y roles | Se conservan; no tienen cuota fija propia en esta configuración |
| OpenAI / Bedrock On-Demand | No hay consumo de inferencia si no hay llamadas |

No tenemos NAT Gateway ni balanceador, que introducirían costes adicionales.
Los snapshots o servicios que se añadan posteriormente se deben revisar por separado.
La pausa busca un coste residual pequeño, no coste cero. La facturación central
puede contener además consumos de otras cuentas y proyectos.

Para este DEV, 30 GiB gp3 a una referencia de 0,088 USD/GiB-mes en Irlanda equivalen
a unos 2,64 USD al mes de discos, incluso con EC2 parada todo el mes. Añadir ECR,
S3 y copias: el total depende de su almacenamiento real y de las tarifas vigentes.
El tamaño que muestra Docker Desktop no es directamente la cantidad facturada por
ECR; no sumar sin más los tamaños de las dos imágenes locales. Revisar Billing por
cuenta y servicio antes de dar una cifra de gasto real.

## Por qué no usamos terraform destroy como pausa

Destruir y reconstruir la máquina elimina su disco de sistema, donde están las
imágenes locales y los certificados Caddy. También obliga a preparar y comprobar
de nuevo el host. El volumen de datos tiene protección contra destrucción, pero
eso no convierte una retirada completa en una operación de pausa.

Terraform tiene `prevent_destroy` en la instancia y el disco de datos para evitar
eliminaciones accidentales. El script no cambia esa protección ni borra recursos.
Eliminar VPC, roles o repositorios no aporta ahorro significativo al modo pausado;
los costes residuales principales son los datos conservados.

Si se necesita coste cercano a cero durante meses, hay que diseñar una retirada:
copias verificadas fuera de AWS, conservación segura de secretos, eliminación
controlada de discos/imágenes/copias y posterior reconstrucción. Guardar snapshots
en AWS también cuesta dinero. El estado Terraform por sí solo no recupera el
contenido de ChromaDB, los documentos, los certificados ni las claves.

## Salvaguardas y límites del script

- Cuenta permitida: DEV `086358667619`, región fija Irlanda. Rechaza PROD y cuentas
  centrales aunque se seleccione un perfil incorrecto.
- Encuentra una única instancia por etiquetas del proyecto y entorno. Si hay cero
  o varias, falla sin actuar. Se puede indicar `-InstanceId i-...`; también valida
  las etiquetas antes de modificarla.
- Permite previsualizar: `.\deploy\dev.ps1 pause -WhatIf` (consulta AWS sin parar).
- Si ya está detenida/arrancada, no repite la operación de parada/arranque.
- No necesita Terraform, SSH ni el PEM para cambiar el estado de EC2.
- No modifica los permisos web ni el estado Terraform. Al ejecutar un nuevo plan,
  Terraform refresca la información real; una IP almacenada en outputs puede estar
  desactualizada hasta ese refresco. Utilizar la IP mostrada por el script o EC2.
- No es un planificador automático: para paradas nocturnas programadas se puede
  añadir después EventBridge Scheduler y permisos específicos.

Referencias: [parada y arranque EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html),
[precios ECR](https://aws.amazon.com/ecr/pricing/) y
[referencia de tarifa gp3 Irlanda](https://aws.amazon.com/blogs/aws-cloud-financial-management/finding-savings-from-2020-reinvent-announcements/).
