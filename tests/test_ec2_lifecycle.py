"""Ciclo de vida EC2 del pipeline con AWS simulado, sin llamadas de red."""

import json

import pytest

from deploy import ec2_lifecycle as lifecycle


TAG = 'sha-' + 'b' * 40 + '-456-1'


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    state = {'power': 'stopped', 'ssm_online': True, 'result': 'Success',
             'wrong_account': False, 'wrong_tags': False, 'start_error': False,
             'missing_invocation': False}
    calls = []

    def fake_aws(*args):
        calls.append(args)
        operation = args[:2]
        if operation == ('sts', 'get-caller-identity'):
            return {'Account': 'other' if state['wrong_account'] else lifecycle.ACCOUNT,
                    'Arn': f'arn:aws:sts::{lifecycle.ACCOUNT}:assumed-role/homologaciones-dev-github-deploy/test'}
        if operation == ('ec2', 'describe-instances'):
            return {'Reservations': [{'Instances': [{
                'InstanceId': lifecycle.INSTANCE, 'State': {'Name': state['power']},
                'Tags': [{'Key': 'Project', 'Value': 'other' if state['wrong_tags'] else 'homologaciones'},
                         {'Key': 'Environment', 'Value': 'dev'}],
            }]}]}
        if operation == ('ec2', 'start-instances'):
            state['power'] = 'running'
            if state['start_error']:
                raise lifecycle.LifecycleError('Respuesta de arranque perdida')
            return {}
        if operation == ('ec2', 'stop-instances'):
            state['power'] = 'stopped'
            return {}
        if operation == ('ec2', 'describe-instance-status'):
            return {'InstanceStatuses': [{'SystemStatus': {'Status': 'ok'}, 'InstanceStatus': {'Status': 'ok'}}]}
        if operation == ('ssm', 'describe-instance-information'):
            return {'InstanceInformationList': [{'InstanceId': lifecycle.INSTANCE,
                                                 'PingStatus': 'Online' if state['ssm_online'] else 'Offline'}]}
        if operation == ('ssm', 'send-command'):
            return {'Command': {'CommandId': 'test-command'}}
        if operation == ('ssm', 'get-command-invocation'):
            if state['missing_invocation']:
                state['missing_invocation'] = False
                raise lifecycle.LifecycleError('Aun no visible', 'InvocationDoesNotExist')
            return {'Status': state['result'], 'ResponseCode': 0 if state['result'] == 'Success' else 1}
        raise AssertionError(f'Operacion inesperada: {args}')

    def fast_wait(check, deadline, message):
        for _ in range(3):
            result = check()
            if result:
                return result
        raise lifecycle.LifecycleError(message)

    monkeypatch.setattr(lifecycle, 'aws', fake_aws)
    monkeypatch.setattr(lifecycle, 'wait_for', fast_wait)
    return tmp_path / 'lifecycle.json', state, calls


def operations(calls):
    return [args[:2] for args in calls]


def test_stopped_instance_is_started_deployed_and_stopped_again(cloud):
    path, state, calls = cloud
    lifecycle.prepare(path)
    lifecycle.execute(path, TAG)
    lifecycle.restore(path)
    assert state['power'] == 'stopped'
    assert operations(calls).count(('ec2', 'start-instances')) == 1
    assert operations(calls).count(('ec2', 'stop-instances')) == 1
    record = lifecycle.load_state(path)
    assert record['initial_state'] == 'stopped'
    assert record['deployment_succeeded'] and record['restored']
    send = next(call for call in calls if call[:2] == ('ssm', 'send-command'))
    assert send[send.index('--document-name') + 1] == lifecycle.DOCUMENT
    assert json.loads(send[send.index('--parameters') + 1]) == {'ImageTag': [TAG]}


def test_running_instance_remains_running(cloud):
    path, state, calls = cloud
    state['power'] = 'running'
    lifecycle.prepare(path)
    lifecycle.execute(path, TAG)
    lifecycle.restore(path)
    assert state['power'] == 'running'
    assert ('ec2', 'start-instances') not in operations(calls)
    assert ('ec2', 'stop-instances') not in operations(calls)


def test_remote_failure_still_allows_cleanup_to_stop_initially_paused_instance(cloud):
    path, state, _ = cloud
    state['result'] = 'Failed'
    lifecycle.prepare(path)
    with pytest.raises(lifecycle.LifecycleError, match='despliegue SSM ha fallado'):
        lifecycle.execute(path, TAG)
    lifecycle.restore(path)
    assert state['power'] == 'stopped'
    assert not lifecycle.load_state(path).get('deployment_succeeded')


def test_lost_start_response_is_recorded_for_cleanup(cloud):
    path, state, _ = cloud
    state['start_error'] = True
    with pytest.raises(lifecycle.LifecycleError, match='arranque perdida'):
        lifecycle.prepare(path)
    assert lifecycle.load_state(path)['start_attempted']
    lifecycle.restore(path)
    assert state['power'] == 'stopped'


def test_ssm_offline_fails_and_machine_can_be_stopped(cloud):
    path, state, _ = cloud
    state['ssm_online'] = False
    with pytest.raises(lifecycle.LifecycleError, match='SSM no esta Online'):
        lifecycle.prepare(path)
    lifecycle.restore(path)
    assert state['power'] == 'stopped'


@pytest.mark.parametrize('flag', ['wrong_account', 'wrong_tags'])
def test_identity_guard_does_not_start_instance(cloud, flag):
    path, state, calls = cloud
    state[flag] = True
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.prepare(path)
    assert not path.exists()
    assert ('ec2', 'start-instances') not in operations(calls)


def test_invalid_tag_cannot_send_a_command(cloud):
    path, _, calls = cloud
    lifecycle.prepare(path)
    with pytest.raises(lifecycle.LifecycleError, match='Etiqueta'):
        lifecycle.execute(path, 'latest; arbitrary-command')
    assert ('ssm', 'send-command') not in operations(calls)


def test_eventual_consistency_of_ssm_is_retried(cloud):
    path, state, _ = cloud
    state['missing_invocation'] = True
    lifecycle.prepare(path)
    lifecycle.execute(path, TAG)
    assert lifecycle.load_state(path)['deployment_succeeded']


def test_restoring_twice_does_not_stop_instance_started_later_by_someone_else(cloud):
    path, state, calls = cloud
    lifecycle.prepare(path)
    lifecycle.restore(path)
    state['power'] = 'running'
    lifecycle.restore(path)
    assert operations(calls).count(('ec2', 'stop-instances')) == 1
    assert state['power'] == 'running'


def test_missing_state_is_noop(cloud):
    path, _, calls = cloud
    lifecycle.restore(path)
    assert not calls


def test_mismatching_state_cannot_operate_another_instance(cloud):
    path, _, calls = cloud
    lifecycle.save_state(path, {'account': lifecycle.ACCOUNT, 'instance': 'i-other'})
    with pytest.raises(lifecycle.LifecycleError, match='no corresponde a DEV'):
        lifecycle.restore(path)
    assert not calls
