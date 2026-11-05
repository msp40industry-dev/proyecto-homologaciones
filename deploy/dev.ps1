<#
.SYNOPSIS
Consulta, detiene o arranca la EC2 de DEV conservando sus discos.
.EXAMPLE
.\deploy\dev.ps1 status
.EXAMPLE
.\deploy\dev.ps1 pause
.EXAMPLE
.\deploy\dev.ps1 resume -UpdateDns
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('status', 'pause', 'resume', 'start', 'stop')]
    [string]$Action,

    [string]$Profile = 'homologaciones-dev',

    [ValidatePattern('^i-[0-9a-f]+$')]
    [string]$InstanceId,

    [switch]$UpdateDns
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$region = 'eu-west-1'
$accountId = '086358667619'
$domain = 'upgradewith-ai.duckdns.org'
# Mantener start/stop como alias compatibles con las instrucciones anteriores.
$operation = switch ($Action) {
    'pause' { 'stop' }
    'resume' { 'start' }
    default { $Action }
}

function Invoke-DevAws {
    param([string[]]$Arguments)
    $result = & aws @Arguments --profile $Profile --region $region --output json --no-cli-pager
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI ha fallado. Comprueba la sesion con: aws login --profile $Profile"
    }
    if ($result) {
        return (($result -join "`n") | ConvertFrom-Json)
    }
}

function Get-DevInstance {
    if ($InstanceId) {
        $response = Invoke-DevAws -Arguments @('ec2', 'describe-instances', '--instance-ids', $InstanceId)
    }
    else {
        $response = Invoke-DevAws -Arguments @(
            'ec2', 'describe-instances', '--filters',
            'Name=tag:Name,Values=homologaciones-dev',
            'Name=tag:Project,Values=homologaciones',
            'Name=tag:Environment,Values=dev',
            'Name=instance-state-name,Values=pending,running,stopping,stopped'
        )
    }
    $instances = @($response.Reservations | ForEach-Object { $_.Instances })
    if ($instances.Count -ne 1) {
        throw "Se esperaba exactamente una EC2 DEV; se encontraron $($instances.Count). Revisa la consola antes de actuar."
    }
    $instance = $instances[0]
    $projectTag = @($instance.Tags | Where-Object { $_.Key -eq 'Project' -and $_.Value -eq 'homologaciones' })
    $environmentTag = @($instance.Tags | Where-Object { $_.Key -eq 'Environment' -and $_.Value -eq 'dev' })
    if ($projectTag.Count -ne 1 -or $environmentTag.Count -ne 1) {
        throw 'La instancia no tiene las etiquetas del proyecto DEV. No se realizara ninguna accion.'
    }
    return $instance
}

function Show-DevInstance {
    param($Instance)
    $publicIp = $Instance.PSObject.Properties['PublicIpAddress']
    $ipText = if ($publicIp) { $publicIp.Value } else { '(sin IP publica)' }
    Write-Host "Cuenta: $accountId | Region: $region"
    Write-Host "EC2: $($Instance.InstanceId) | Estado: $($Instance.State.Name)"
    Write-Host "IP publica: $ipText"
    if ($Instance.State.Name -eq 'stopped') {
        Write-Host 'Computo detenido. EBS, ECR, S3 y copias conservadas siguen generando costes.'
    }
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw 'No se encuentra AWS CLI en el Path.'
}
if ($UpdateDns -and $operation -ne 'start') {
    throw '-UpdateDns solo se utiliza con resume (o su alias start).'
}
if ($UpdateDns -and [string]::IsNullOrWhiteSpace($env:DUCKDNS_TOKEN)) {
    throw 'Para -UpdateDns, cargar DUCKDNS_TOKEN en esta terminal. No guardarlo en Git ni en los argumentos.'
}

$identity = Invoke-DevAws -Arguments @('sts', 'get-caller-identity')
if ($identity.Account -ne $accountId) {
    throw "Cuenta incorrecta: $($identity.Account). Solo se permite DEV ($accountId)."
}
$instance = Get-DevInstance
Show-DevInstance $instance
if ($operation -eq 'status') { return }

if (-not $PSCmdlet.ShouldProcess("DEV $($instance.InstanceId)", $Action)) { return }

$targetId = $instance.InstanceId
if ($operation -eq 'stop') {
    if ($instance.State.Name -eq 'pending') {
        Write-Host 'Esperando a que finalice el arranque antes de detener...'
        Invoke-DevAws -Arguments @('ec2', 'wait', 'instance-running', '--instance-ids', $targetId) | Out-Null
        $instance = Get-DevInstance
    }
    if ($instance.State.Name -eq 'running') {
        Write-Host 'Solicitando parada normal de Ubuntu y esperando a stopped...'
        Invoke-DevAws -Arguments @('ec2', 'stop-instances', '--instance-ids', $targetId) | Out-Null
    }
    elseif ($instance.State.Name -notin @('stopping', 'stopped')) {
        throw "No se puede detener desde el estado $($instance.State.Name)."
    }
    Invoke-DevAws -Arguments @('ec2', 'wait', 'instance-stopped', '--instance-ids', $targetId) | Out-Null
    Show-DevInstance (Get-DevInstance)
    Write-Host 'Los archivos de disco se conservan; las sesiones y revisiones en memoria se pierden.'
    return
}

if ($instance.State.Name -eq 'stopping') {
    Write-Host 'Esperando a que finalice la parada...'
    Invoke-DevAws -Arguments @('ec2', 'wait', 'instance-stopped', '--instance-ids', $targetId) | Out-Null
    $instance = Get-DevInstance
}
if ($instance.State.Name -eq 'stopped') {
    Write-Host 'Arrancando EC2 y esperando comprobaciones de sistema...'
    Invoke-DevAws -Arguments @('ec2', 'start-instances', '--instance-ids', $targetId) | Out-Null
}
elseif ($instance.State.Name -notin @('running', 'pending')) {
    throw "No se puede arrancar desde el estado $($instance.State.Name)."
}
Invoke-DevAws -Arguments @('ec2', 'wait', 'instance-running', '--instance-ids', $targetId) | Out-Null
Invoke-DevAws -Arguments @('ec2', 'wait', 'instance-status-ok', '--instance-ids', $targetId) | Out-Null
$instance = Get-DevInstance
Show-DevInstance $instance
$ip = $instance.PSObject.Properties['PublicIpAddress']
if (-not $ip) { throw 'EC2 ha arrancado sin IPv4 publica. Revisar antes de actualizar DNS.' }

if ($UpdateDns) {
    $escapedToken = [Uri]::EscapeDataString($env:DUCKDNS_TOKEN)
    $dnsUri = "https://www.duckdns.org/update?domains=upgradewith-ai&token=$escapedToken&ip=$($ip.Value)"
    try {
        $response = Invoke-RestMethod -Uri $dnsUri -Method Get -TimeoutSec 30
        if ([string]$response -notmatch '^OK\s*$') { throw 'DNS no confirmado' }
    }
    catch {
        # No propagar la excepcion HTTP: podria incluir el token de la URL.
        throw 'EC2 esta arrancada, pero DuckDNS no se ha actualizado. Revisar el token o actualizar la IP manualmente.'
    }
    Write-Host 'DuckDNS actualizado. La propagacion DNS puede tardar.'
}
else {
    Write-Host "Actualizar DuckDNS a $($ip.Value) si ha cambiado la IP. Tambien puedes repetir resume con -UpdateDns."
}
Write-Host "EC2 esta operativa; comprueba https://$domain y la salud de los tres contenedores."
Write-Host 'Docker debe reanudar los contenedores existentes salvo que se hubieran detenido manualmente.'
