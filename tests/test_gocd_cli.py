import os

import pytest
from mock import MagicMock

from gocd import Server
from gocd.api import Pipeline
import gocd_cli


@pytest.fixture
def args_positional():
    return ('pipeline', 'retrigger-failed', 'Simple-with-lock')


@pytest.fixture
def args():
    return (
        'pipeline',
        'retrigger-failed',
        'Simple-with-lock',
        '--stage=firstStage',
        '--retrigger',
        'stage',
    )


@pytest.fixture
def go_server():
    server = MagicMock(spec=Server)
    server.pipeline.return_value = MagicMock(spec=Pipeline)

    return server


def support_path(file='gocd-cli.cfg'):
    return os.path.join(os.path.dirname(__file__), 'support', file)


def test_format_arguments():
    args, kwargs = gocd_cli.format_arguments(
        'name',
        '--stage=firstStage',
        '--retrigger',
        'stage',
        '--pipeline-name=Simple-with-lock',
        'some-other',
    )

    assert args == ['name', 'some-other']
    assert kwargs == {
        'stage': 'firstStage',
        'retrigger': 'stage',
        'pipeline_name': 'Simple-with-lock'
    }


def test_get_command_successfully_sets_all_args(args):
    go_server = Server('http://localhost:8153')
    command = gocd_cli.get_command(go_server, *args)

    assert command.pipeline.name == 'Simple-with-lock'
    assert command.stage == 'firstStage'
    assert command.retrigger_type == 'stage'


def test_get_command_raises_reasonable_errors(go_server):
    with pytest.raises(ImportError) as exc:
        gocd_cli.get_command(go_server, 'no-such-module', 'retrigger-failed')
    assert 'gocd_cli.commands:' in str(exc)

    with pytest.raises(AttributeError) as exc:
        gocd_cli.get_command(go_server, 'pipeline', 'no-such-command')
    assert 'gocd_cli.commands.pipeline' in str(exc)
    assert 'object has no attribute \'NoSuchCommand\'' in str(exc)

    with pytest.raises(TypeError) as exc:
        gocd_cli.get_command(go_server, 'pipeline', 'retrigger-failed')
    assert 'RetriggerFailed' in str(exc)
    assert '__init__() takes at least 3 arguments (2 given)' in str(exc)


class TestIsFileReadable(object):
    def test_normal_file(self):
        assert gocd_cli.is_file_readable(support_path())

    def test_directory(self):
        assert not gocd_cli.is_file_readable(os.path.dirname(support_path()))

    def test_expands_home_directory(self, monkeypatch):
        path = '~/test-random-0123'
        expanded_path = os.path.expanduser(path)

        monkeypatch.setattr(os.path, 'isfile', lambda p: True if p == expanded_path else False)
        monkeypatch.setattr(os, 'access', lambda p, _: True if p == expanded_path else False)

        assert gocd_cli.is_file_readable(path)


class TestGetSettings(object):
    def test_get_settings_with_config_file(self, monkeypatch):
        monkeypatch.delenv('GOCD_SERVER', raising=False)
        monkeypatch.setattr(os, 'access', lambda _, __: False)
        settings = gocd_cli.get_settings()

        assert settings.get('server') is None

    def test_get_settings_from_first_config_file(self, monkeypatch):
        monkeypatch.delenv('GOCD_SERVER', raising=False)
        settings = gocd_cli.get_settings(settings_paths=support_path())

        assert settings.get('server') == 'http://localhost:8153'

    def test_get_settings_from_second_file(self, monkeypatch):
        monkeypatch.delenv('GOCD_SERVER', raising=False)
        settings = gocd_cli.get_settings(settings_paths=(
            support_path('gocd-non-existent.cfg'),
            support_path('gocd-cli-alternative.cfg')
        ))

        assert settings.get('server') == 'http://goserver.dev'

    def test_only_try_to_read_files_not_dirs(self, monkeypatch):
        monkeypatch.delenv('GOCD_SERVER', raising=False)
        settings = gocd_cli.get_settings(settings_paths=os.path.dirname(support_path()))

        assert settings.get('server') is None

    def test_prefer_environment_variable(self, monkeypatch):
        monkeypatch.setenv('GOCD_SERVER', 'http://go.cd')
        settings = gocd_cli.get_settings(settings_paths=support_path())

        assert settings.get('server') == 'http://go.cd'


class TestGetGoServer(object):
    def test_get_server_with_a_given_settings_object(self):
        settings = gocd_cli.get_settings(settings_paths=support_path())
        go_server = gocd_cli.get_go_server(settings=settings)

        assert go_server.host == settings.get('server')
        assert go_server.user == settings.get('user')

    def test_get_a_server_with_default_get_settings_object(self, monkeypatch):
        settings = gocd_cli.get_settings(settings_paths=support_path('gocd-cli-alternative.cfg'))
        monkeypatch.setattr(gocd_cli, 'get_settings', lambda *args: settings)

        go_server = gocd_cli.get_go_server()

        assert go_server.host == settings.get('server')
        assert go_server.user == settings.get('user')