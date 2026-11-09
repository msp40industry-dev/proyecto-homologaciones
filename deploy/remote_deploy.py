"""Despliegue fijo de DEV, incluido por Terraform en un documento SSM.

No recibe comandos, URLs, rutas ni secretos del workflow. Solo una etiqueta de
las imágenes del pipeline; el entorno y los datos permanecen en el servidor.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


APP_DIR = Path('/srv/homologaciones/app')
REGISTRY = '086358667619.dkr.ecr.eu-west-1.amazonaws.com'
IMAGE_TAG_PATTERN = r'sha-[0-9a-f]{40}-[0-9]+-[0-9]+'
COMPOSE_FILES = ('compose.ec2.yml', 'compose.public.yml')


class DeploymentError(RuntimeError):
    pass


def validate_tag(tag):
    if not re.fullmatch(IMAGE_TAG_PATTERN, tag):
        raise DeploymentError('Etiqueta no valida: se requiere una version del pipeline de main.')


def update_image_references(text, tag):
    """Conservar el entorno, sustituyendo solo las referencias de las imágenes."""
    validate_tag(tag)
    replacements = {
        'BACKEND_IMAGE': f'{REGISTRY}/homologaciones-dev/backend:{tag}',
        'FRONTEND_IMAGE': f'{REGISTRY}/homologaciones-dev/frontend:{tag}',
    }
    output = []
    seen = set()
    for line in text.splitlines(keepends=True):
        match = re.match(r'^\s*(?:export\s+)?(BACKEND_IMAGE|FRONTEND_IMAGE)\s*=', line)
        if match:
            key = match.group(1)
            if key not in seen:
                output.append(f'{key}={replacements[key]}\n')
                seen.add(key)
        else:
            output.append(line)
    result = ''.join(output)
    if result and not result.endswith('\n'):
        result += '\n'
    for key, value in replacements.items():
        if key not in seen:
            result += f'{key}={value}\n'
    return result


def command(args, *, env=None, input_text=None):
    """No volcar stderr, config resuelta ni respuestas con posibles secretos."""
    try:
        result = subprocess.run(
            args, env=env, input=input_text, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError(f'No se pudo completar la operacion {args[0]}.') from exc
    if result.returncode:
        raise DeploymentError(f'Operacion {args[0]} fallida (codigo {result.returncode}).')
    return result.stdout.strip()


def write_atomic(path, text):
    if path.is_symlink():
        raise DeploymentError('No se permiten enlaces simbolicos en la configuracion.')
    stat = path.stat() if path.exists() else path.parent.stat()
    # Mantener propietario y no ampliar los permisos del archivo existente.
    mode = (stat.st_mode & 0o640) if path.exists() else 0o640
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), mode)
            os.fchown(handle.fileno(), stat.st_uid, stat.st_gid)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def verify_host():
    if os.geteuid() != 0:
        raise DeploymentError('El documento SSM debe ejecutarse como root.')
    command(['mountpoint', '-q', '/srv/homologaciones'])
    account = command(['aws', 'sts', 'get-caller-identity', '--region', 'eu-west-1',
                       '--query', 'Account', '--output', 'text'])
    if account != '086358667619':
        raise DeploymentError('Cuenta AWS inesperada.')


def deploy_release(tag, bundle, app_dir=APP_DIR):
    validate_tag(tag)
    if set(bundle) != set(COMPOSE_FILES):
        raise DeploymentError('El documento no incluye las dos configuraciones Compose esperadas.')
    paths = [app_dir / '.env.dev'] + [app_dir / name for name in COMPOSE_FILES]
    if not app_dir.is_dir() or any(path.is_symlink() or not path.is_file() for path in paths):
        raise DeploymentError('Falta configuracion remota o contiene enlaces simbolicos.')

    # Solo en memoria; nunca se imprimen ni se envían a GitHub los secretos.
    previous = {path: path.read_text(encoding='utf-8') for path in paths}
    updated_env = update_image_references(previous[paths[0]], tag)
    child_env = dict(os.environ)
    child_env['APP_ENV_FILE'] = str(paths[0])
    for key in ('BACKEND_IMAGE', 'FRONTEND_IMAGE', 'COMPOSE_FILE',
                'COMPOSE_PROJECT_NAME', 'DOCKER_HOST', 'DOCKER_CONTEXT'):
        child_env.pop(key, None)
    compose = ['docker', 'compose', '--project-directory', str(app_dir),
               '--env-file', str(paths[0]), '-f', str(paths[1]), '-f', str(paths[2])]

    def run_compose(*args):
        return command(compose + list(args), env=child_env)

    def check_services():
        for service in ('backend', 'frontend', 'caddy'):
            ids = run_compose('ps', '--all', '--quiet', service).split()
            if len(ids) != 1:
                raise DeploymentError(f'Se esperaba un contenedor para {service}.')
            states = json.loads(command(['docker', 'inspect', '--format', '{{json .State}}', ids[0]],
                                        env=child_env))
            if not states.get('Running'):
                raise DeploymentError(f'El servicio {service} no esta ejecutandose.')
            if service != 'caddy' and states.get('Health', {}).get('Status') != 'healthy':
                raise DeploymentError(f'El servicio {service} no supera el healthcheck.')

    # Comprobar la configuración anterior antes de tocar archivos o contenedores.
    run_compose('config', '--quiet')
    password = command(['aws', 'ecr', 'get-login-password', '--region', 'eu-west-1'])
    command(['docker', 'login', '--username', 'AWS', '--password-stdin', REGISTRY],
            env=child_env, input_text=password + '\n')
    del password

    changed = False
    recreate_attempted = False
    try:
        changed = True
        write_atomic(paths[0], updated_env)
        for name in COMPOSE_FILES:
            write_atomic(app_dir / name, bundle[name])
        run_compose('config', '--quiet')
        run_compose('pull', 'backend', 'frontend')
        recreate_attempted = True
        run_compose('up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '180')
        check_services()
    except Exception as exc:
        if changed:
            try:
                for path, content in previous.items():
                    write_atomic(path, content)
                if recreate_attempted:
                    run_compose('up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '180')
                    check_services()
            except Exception:
                raise DeploymentError('Despliegue fallido y restauracion incompleta; revisar la EC2.') from None
        raise DeploymentError('Despliegue fallido; configuracion anterior restaurada.') from exc

    print(f'Despliegue correcto: {tag}. Backend/frontend healthy; Caddy running.')


def main():
    import fcntl

    verify_host()
    tag = os.environ.get('SSM_ImageTag', '')
    validate_tag(tag)
    # fcntl libera el bloqueo al terminar, incluso ante errores del proceso.
    with open('/run/homologaciones-dev-deploy.lock', 'a', encoding='utf-8') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeploymentError('Ya existe un despliegue en curso.') from None
        deploy_release(tag, globals()['_DEPLOY_BUNDLE'])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Los mensajes propios son seguros; no imprimir errores de terceros.
        message = str(error) if isinstance(error, DeploymentError) else 'Error interno del despliegue.'
        print(message, file=sys.stderr)
        sys.exit(1)
