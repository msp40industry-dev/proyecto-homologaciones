# Cuentas, roles y acceso al equipo AWS

Esta guía describe la configuración del equipo. La cuenta personal utilizada para
el piloto anterior es independiente y no se utiliza para los despliegues actuales.

## 1. Mapa de cuentas

| Cuenta | Identificador | Responsabilidad |
|---|---|---|
| Management Account | `134129017172` | Organización, políticas, facturación consolidada y presupuestos |
| Identity Delegated Admin | `369970405121` | Administración delegada de identidades y accesos |
| DEV | `086358667619` | Desarrollo y pruebas |
| PROD | `621555631629` | Producción |

Idea Launchpad es otra cuenta existente del equipo; no interviene en este despliegue.
Los recursos de la aplicación se desplegarán en Irlanda (`eu-west-1`). La instancia
de organización de IAM Identity Center está en Virginia (`us-east-1`); esta región
de administración de identidades es independiente de la región de la aplicación.

## 2. Identidad, cuenta, rol y perfil local

- **Builder ID:** identifica a la persona. Cada socio utiliza sus propias
  credenciales y MFA. No es una cuenta AWS que contenga máquinas o discos.
- **Cuenta AWS:** contiene los recursos y sus consumos. En AWS Settings, los
  proyectos agrupan una cuenta y su configuración de colaboración. Acceder con
  un correo personal no convierte los recursos del equipo en recursos personales.
- **Rol IAM:** identidad temporal con permisos dentro de una cuenta. Existe un
  `TeamAdministratorAccess` en DEV y otro independiente en PROD, con la política
  `AdministratorAccess`. No aparecen en IAM → Roles de las cuentas centrales.
- **Asignación de acceso:** Account Access Manager conecta el usuario del equipo
  con el rol de una cuenta. IAM Identity Center gestiona las identidades.
- **Perfil CLI:** nombre de configuración en el ordenador, como
  `homologaciones-dev`. El nombre no garantiza la cuenta elegida: comprobarla con
  `aws sts get-caller-identity`.

Las políticas de organización (SCP) pueden restringir acciones incluso a un rol
administrativo. La autorización de Irlanda se configuró a ese nivel; añadir
permisos al rol no anula una prohibición de la organización.

## 3. Enlaces e identidad que utilizar

| Tarea / favorito | Identidad utilizada actualmente | Destino |
|---|---|---|
| 1. Gestión del equipo | Identidad administrativa del equipo | https://settings.aws.com/projects |
| 2. Acceso DEV y PROD | Builder ID individual | Account access URL de la organización |
| 3. Administración de accesos | Identidad administrativa del equipo | Identity Delegated Admin → IAM Identity Center / Account Access Manager |
| 4. Organización y políticas | Identidad administrativa del equipo | Management Account → AWS Organizations |
| 5. Facturación | Identidad administrativa del equipo | Management Account → Billing and Cost Management |

Desde AWS Settings, la identidad administrativa abre Identity Delegated Admin con
AWS Console o Management Account con Centrally manage your organization. La
identidad individual ve DEV y PROD según sus asignaciones. Para inventariar todas
las cuentas, consultar AWS Organizations desde Management.

El Account access URL se obtiene en Account Access Manager → Settings. Guardarlo
como favorito; no usar una URL temporal de sesión de consola como sustituto.
Separar los perfiles de navegador de administración e identidad individual ayuda
a evitar autorizar por error la cuenta central desde la CLI.

Los accesos individuales a las cuentas centrales requieren asignaciones adicionales;
no se conceden automáticamente al asignar DEV o PROD. La identidad administrativa
del equipo no debe confundirse con el usuario raíz de una cuenta AWS.

## 4. Incorporar a un socio

1. Con la identidad administrativa, abrir Identity Delegated Admin → IAM Identity
   Center en Virginia → Users → Invite new team member. Si se está en Account
   Access Manager → Users, pulsar Manage in IAM Identity Center para llegar allí.
2. Invitar el correo individual del socio. El socio acepta con su Builder ID y
   configura MFA. Revisar Manage invitations si la incorporación sigue pendiente.
3. En IAM Identity Center → Users, comprobar su correo y Display name.
4. En Account Access Manager → Accounts → DEV → Assign new access, buscar ese
   Display name y seleccionar al usuario. Introducir `TeamAdministratorAccess`
   como IAM role name. Repetir en PROD si se le concederá también ese acceso.
5. El socio abre el Account access URL con su identidad individual y prueba el
   rol de cada cuenta. En la consola, comprobar identificador y acceso a EC2 en
   Irlanda. El acceso AWS de los socios es distinto de los usuarios de la aplicación.

## 5. Comprobar el acceso desde PowerShell

Instalar AWS CLI actual; `aws login` requiere versión 2.32.0 o posterior.

```powershell
aws login --profile homologaciones-dev
aws sts get-caller-identity --profile homologaciones-dev
```

Usar `eu-west-1` cuando pregunte la región. En el navegador, seleccionar DEV
(`086358667619`) con `TeamAdministratorAccess`. Si ofrece sobrescribir un perfil,
comprobar la cuenta de destino antes de aceptar: el navegador puede contener
sesiones centrales abiertas.

Resultado esperado: Account = `086358667619` y Arn con
`assumed-role/TeamAdministratorAccess/`. Para PROD, usar un perfil separado
`homologaciones-prod` y comprobar Account = `621555631629`.

La [guía de infraestructura](../infra/README.md) explica el perfil auxiliar
`homologaciones-dev-terraform`, que reutiliza la sesión temporal mediante
`credential_process`. No crea un usuario ni un rol nuevo. Renovar la sesión con
`aws login` cuando caduque; no guardar claves en los archivos Terraform.

## 6. Facturación y presupuestos

La facturación se centraliza en Management. Desde esa cuenta se crean presupuestos
filtrados por Linked account para vigilar DEV y PROD por separado. Los correos de
los usuarios son identidades de acceso, no destinatarios automáticos de los cargos.

Se configuró un presupuesto DEV de 20 USD mensuales con avisos de consumo real
al 50 %, 80 % y 100 %. El presupuesto PROD quedó pendiente de que la cuenta
apareciera en el filtro; comprobar la consola antes de darlo por creado.
Los avisos no impiden superar el presupuesto ni apagan automáticamente recursos.
