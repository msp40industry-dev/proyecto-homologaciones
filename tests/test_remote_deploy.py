"""Documento SSM: pruebas con Docker/AWS simulados, sin tocar un servidor."""

import json
import pytest

from deploy import remote_deploy as deploy


TAG = 'sha-' + 'a' * 40 + '-123-1'


@pytest.mark.parametrize('tag', ['latest', '../escape', TAG + ';id', '', 'sha-short-1-1'])
def test_rejects_invalid_tags(tag):
    with pytest.raises(deploy.DeploymentError):
        deploy.validate_tag(tag)


def test_env_preserves_secrets_and_other_settings():
    text = '# entorno\nOPENAI_API_KEY=placeholder\nPUBLIC_DOMAIN=test.example\nBACKEND_IMAGE=old\nBACKEND_IMAGE=duplicate\n'
    updated = deploy.update_image_references(text, TAG)
    assert 'OPENAI_API_KEY=placeholder\nPUBLIC_DOMAIN=test.example\n' in updated
    assert updated.count('BACKEND_IMAGE=') == 1
    assert f'BACKEND_IMAGE={deploy.REGISTRY}/homologaciones-dev/backend:{TAG}\n' in updated
    assert f'FRONTEND_IMAGE={deploy.REGISTRY}/homologaciones-dev/frontend:{TAG}\n' in updated


@pytest.fixture
def remote(tmp_path, monkeypatch):
    previous = {
        '.env.dev': 'OPENAI_API_KEY=placeholder\nBACKEND_IMAGE=old-back\nFRONTEND_IMAGE=old-front\n',
        'compose.ec2.yml': 'old-private',
        'compose.public.yml': 'old-public',
    }
    for name, text in previous.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    calls = []
    failure = {'phase': None, 'remaining': 1}

    def fake_command(args, *, env=None, input_text=None):
        calls.append(args)
        if args[:3] == ['aws', 'ecr', 'get-login-password']:
            return 'temporary-password'
        if args[:2] == ['docker', 'inspect']:
            return json.dumps({'Running': True, 'Health': {'Status': 'healthy'}})
        if args[:2] == ['docker', 'compose']:
            # Buscar los argumentos de operación después de los dos Compose.
            operation_index = max(i for i, value in enumerate(args) if value == '-f') + 2
            subcommand = args[operation_index:]
            if subcommand[0] == failure['phase'] and failure['remaining']:
                failure['remaining'] -= 1
                raise deploy.DeploymentError('Fallo simulado')
            if subcommand[0] == 'ps':
                return 'container-' + subcommand[-1]
        return ''

    monkeypatch.setattr(deploy, 'command', fake_command)
    bundle = {'compose.ec2.yml': 'new-private', 'compose.public.yml': 'new-public'}
    return tmp_path, previous, bundle, calls, failure


def compose_operations(calls):
    operations = []
    for args in calls:
        if args[:2] == ['docker', 'compose']:
            index = max(i for i, value in enumerate(args) if value == '-f') + 2
            operations.append(args[index:])
    return operations


def test_success_updates_both_images_and_checks_services(remote):
    root, previous, bundle, calls, _ = remote
    deploy.deploy_release(TAG, bundle, root)
    assert 'OPENAI_API_KEY=placeholder' in (root / '.env.dev').read_text()
    assert TAG in (root / '.env.dev').read_text()
    assert (root / 'compose.ec2.yml').read_text() == 'new-private'
    assert (root / 'compose.public.yml').read_text() == 'new-public'
    operations = compose_operations(calls)
    assert ['pull', 'backend', 'frontend'] in operations
    assert ['up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '180'] in operations
    assert len([args for args in calls if args[:2] == ['docker', 'inspect']]) == 3
    assert {path.name for path in root.iterdir()} == set(previous)


@pytest.mark.parametrize('phase,expected_recreations', [('pull', 0), ('up', 2)])
def test_failure_restores_previous_configuration(remote, phase, expected_recreations):
    root, previous, bundle, calls, failure = remote
    failure['phase'] = phase
    with pytest.raises(deploy.DeploymentError, match='configuracion anterior restaurada'):
        deploy.deploy_release(TAG, bundle, root)
    for name, content in previous.items():
        assert (root / name).read_text() == content
    assert len([args for args in compose_operations(calls) if args[0] == 'up']) == expected_recreations


def test_failed_rollback_is_reported(remote):
    root, _, bundle, _, failure = remote
    failure.update(phase='up', remaining=2)
    with pytest.raises(deploy.DeploymentError, match='restauracion incompleta'):
        deploy.deploy_release(TAG, bundle, root)


def test_missing_env_fails_before_aws_or_docker(remote):
    root, _, bundle, calls, _ = remote
    (root / '.env.dev').unlink()
    with pytest.raises(deploy.DeploymentError, match='Falta configuracion'):
        deploy.deploy_release(TAG, bundle, root)
    assert not calls


def test_symlink_env_is_rejected(remote):
    root, _, bundle, calls, _ = remote
    env = root / '.env.dev'
    target = root / 'other.env'
    env.rename(target)
    env.symlink_to(target)
    with pytest.raises(deploy.DeploymentError, match='enlaces simbolicos'):
        deploy.deploy_release(TAG, bundle, root)
    assert not calls
