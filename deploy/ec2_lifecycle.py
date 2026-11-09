"""Orquestación de DEV desde GitHub: preparar, desplegar por SSM y restaurar estado.

Solo usa AWS CLI y la biblioteca estándar. No necesita SSH ni copia secretos del
servidor. El estado temporal permite ejecutar restore como paso always() separado.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ACCOUNT = '086358667619'
REGION = 'eu-west-1'
INSTANCE = 'i-0cfac93db6ece709a'
DOCUMENT = 'homologaciones-dev-deploy'
TERMINAL_COMMAND_STATES = {'Success', 'Failed', 'Cancelled', 'TimedOut'}


class LifecycleError(RuntimeError):
    def __init__(self, message, code=''):
        super().__init__(message)
        self.code = code


def aws(*args):
    try:
        result = subprocess.run(
            ['aws', *args, '--region', REGION, '--output', 'json', '--no-cli-pager',
             '--cli-connect-timeout', '5', '--cli-read-timeout', '20'],
            capture_output=True, text=True, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleError('No se pudo completar una consulta AWS.') from exc
    if result.returncode:
        match = re.search(r'An error occurred \(([^)]+)\)', result.stderr)
        code = match.group(1) if match else 'CLIError'
        raise LifecycleError(f'AWS {args[0]}/{args[1]}: {code}', code)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


def load_state(path):
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('instance') != INSTANCE or state.get('account') != ACCOUNT:
        raise LifecycleError('El registro de despliegue no corresponde a DEV.')
    return state


def get_instance():
    response = aws('ec2', 'describe-instances', '--instance-ids', INSTANCE)
    instances = [instance for reservation in response['Reservations'] for instance in reservation['Instances']]
    if len(instances) != 1:
        raise LifecycleError('Se esperaba exactamente la instancia DEV autorizada.')
    instance = instances[0]
    tags = {item['Key']: item['Value'] for item in instance.get('Tags', [])}
    if instance.get('InstanceId') != INSTANCE or tags.get('Project') != 'homologaciones' or tags.get('Environment') != 'dev':
        raise LifecycleError('La instancia no tiene la identidad y etiquetas de DEV.')
    return instance


def wait_for(check, deadline, message):
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(5)
    raise LifecycleError(message)


def prepare(path):
    identity = aws('sts', 'get-caller-identity')
    prefix = f'arn:aws:sts::{ACCOUNT}:assumed-role/homologaciones-dev-github-deploy/'
    if identity.get('Account') != ACCOUNT or not identity.get('Arn', '').startswith(prefix):
        raise LifecycleError('Se requiere el rol OIDC de despliegue de DEV.')
    if path.exists():
        raise LifecycleError('Ya existe un registro de ciclo de vida para este job.')

    def stable_state():
        value = get_instance()['State']['Name']
        if value in ('terminated', 'shutting-down'):
            raise LifecycleError('La instancia ha sido eliminada o esta terminando.')
        return value if value in ('running', 'stopped') else None

    initial = wait_for(stable_state, time.monotonic() + 300, 'La EC2 no alcanza un estado estable.')
    state = {'account': ACCOUNT, 'instance': INSTANCE, 'initial_state': initial,
             'start_attempted': False, 'restored': False}
    save_state(path, state)
    print(f'Estado inicial de DEV: {initial}', flush=True)
    if initial == 'stopped':
        # Registrar antes de llamar: también se intentará parar si la respuesta
        # del arranque se pierde o falla después de que AWS lo haya aceptado.
        state['start_attempted'] = True
        save_state(path, state)
        aws('ec2', 'start-instances', '--instance-ids', INSTANCE)

    deadline = time.monotonic() + 600
    wait_for(lambda: get_instance()['State']['Name'] == 'running', deadline,
             'La EC2 no ha arrancado dentro del plazo.')

    def system_ready():
        statuses = aws('ec2', 'describe-instance-status', '--instance-ids', INSTANCE).get('InstanceStatuses', [])
        return bool(statuses and statuses[0].get('SystemStatus', {}).get('Status') == 'ok'
                    and statuses[0].get('InstanceStatus', {}).get('Status') == 'ok')

    wait_for(system_ready, deadline, 'Las comprobaciones EC2 no estan listas.')

    def ssm_ready():
        nodes = aws('ssm', 'describe-instance-information', '--filters',
                    f'Key=InstanceIds,Values={INSTANCE}').get('InstanceInformationList', [])
        return any(node.get('InstanceId') == INSTANCE and node.get('PingStatus') == 'Online' for node in nodes)

    wait_for(ssm_ready, deadline, 'El agente SSM no esta Online.')
    print('EC2 y SSM preparados para desplegar.', flush=True)


def wait_command(command_id, deadline):
    def finished():
        try:
            invocation = aws('ssm', 'get-command-invocation', '--command-id', command_id,
                             '--instance-id', INSTANCE)
        except LifecycleError as exc:
            if exc.code == 'InvocationDoesNotExist':
                return None
            raise
        return invocation if invocation.get('Status') in TERMINAL_COMMAND_STATES else None

    return wait_for(finished, deadline, 'No se ha podido confirmar el final del comando SSM.')


def execute(path, tag):
    if not re.fullmatch(r'sha-[0-9a-f]{40}-[0-9]+-[0-9]+', tag):
        raise LifecycleError('Etiqueta de imagen no valida.')
    state = load_state(path)
    if state.get('restored') or state.get('command_id'):
        raise LifecycleError('Este registro ya tiene un comando o esta finalizado.')
    response = aws('ssm', 'send-command', '--instance-ids', INSTANCE,
                   '--document-name', DOCUMENT, '--document-version', '$LATEST',
                   '--timeout-seconds', '120', '--parameters', json.dumps({'ImageTag': [tag]}))
    state['command_id'] = response['Command']['CommandId']
    state['command_sent_at'] = time.time()
    state['image_tag'] = tag
    save_state(path, state)
    print(f'Comando SSM: {state["command_id"]}. Version: {tag}', flush=True)
    invocation = wait_command(state['command_id'], time.monotonic() + 2100)
    print(f'Resultado SSM: {invocation["Status"]}', flush=True)
    if invocation['Status'] != 'Success' or invocation.get('ResponseCode', -1) != 0:
        raise LifecycleError('El despliegue SSM ha fallado; revisar su resultado en Systems Manager.')
    state['deployment_succeeded'] = True
    save_state(path, state)


def restore(path):
    if not path.exists():
        print('No se registro un arranque; no se modifica la EC2.')
        return
    state = load_state(path)
    if state.get('restored'):
        print('El ciclo de vida ya esta finalizado.')
        return
    if state['initial_state'] == 'stopped' and state['start_attempted']:
        if state.get('command_id'):
            # Si el paso anterior falló por un problema de red, dar al documento
            # su ventana de ejecución antes de detener la máquina en mitad del cambio.
            remaining = max(1, state['command_sent_at'] + 2100 - time.time())
            try:
                wait_command(state['command_id'], time.monotonic() + remaining)
            except LifecycleError:
                print('Aviso: no se confirma el final de SSM; se intentara parar DEV para limitar costes.', flush=True)
        deadline = time.monotonic() + 300

        def can_stop():
            value = get_instance()['State']['Name']
            return value if value in ('running', 'stopped', 'stopping') else None

        current = wait_for(can_stop, deadline, 'No se puede confirmar el estado para detener DEV.')
        if current == 'running':
            aws('ec2', 'stop-instances', '--instance-ids', INSTANCE)
        wait_for(lambda: get_instance()['State']['Name'] == 'stopped', deadline,
                 'DEV no ha quedado stopped; revisar AWS para evitar costes.')
        print('DEV vuelve a stopped, como al inicio. EBS/ECR/S3 siguen conservados.', flush=True)
    else:
        print('DEV estaba running; no se solicita apagarla.', flush=True)
    state['restored'] = True
    save_state(path, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('prepare', 'execute', 'restore'))
    parser.add_argument('--state-file', type=Path, required=True)
    parser.add_argument('--image-tag', default='')
    args = parser.parse_args()
    try:
        if args.operation == 'prepare':
            prepare(args.state_file)
        elif args.operation == 'execute':
            execute(args.state_file, args.image_tag)
        else:
            restore(args.state_file)
    except (LifecycleError, OSError, ValueError, KeyError) as exc:
        message = str(exc) if isinstance(exc, LifecycleError) else 'Error al procesar el registro o la respuesta AWS.'
        print(message, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
