from __future__ import print_function

import time

from gocd_cli.command import BaseCommand
from gocd_cli.utils import get_settings

from .check import Check
from .retrigger_failed import RetriggerFailed

__all__ = [
    'Check',
    'CheckAll',
    'List',
    'Pause',
    'RetriggerFailed',
    'Trigger',
    'Unlock',
    'Unpause',
]


def unlock_pipeline(pipeline):
    response = pipeline.status()

    if response and response['locked']:
        return pipeline.unlock()
    else:
        return False


class Trigger(BaseCommand):
    usage = """
    Flags:
        unlock: Whether the pipeline should be unlocked if it's locked.
          Default: false
        variables: A comma separated list of key=value pairs that will
          be passed to the pipeline.
          Example: SHARED_SECRET=Mellon,SECOND=Really Im first
        secure_variables: A comma separated list of key=value pairs.
        wait_until_finished: Will wait until the pipeline finishes running and
          then exit 0 on success, and 2 on failure. The console.log will
          be output for each stage in order.
        verbose: Will print a . every tick when wait_until_finished is true
    """
    usage_summary = 'Triggers the named pipeline'

    _tick = 30  # seconds

    def __init__(self, server, name, unlock=False, variables=None, secure_variables=None,
                 wait_until_finished=False, verbose=False):
        self.pipeline = server.pipeline(name)
        self.unlock = str(unlock).lower().strip() == 'true'
        self.variables = self._convert_to_dict(variables)
        self.secure_variables = self._convert_to_dict(secure_variables)
        self.wait_until_finished = str(wait_until_finished).lower().strip() == 'true'
        self.verbose = str(verbose).lower().strip() == 'true'

    def run(self):
        if self.unlock:
            unlock_pipeline(self.pipeline)

        response = self.pipeline.schedule(
            variables=self.variables,
            secure_variables=self.secure_variables,
            return_new_instance=self.wait_until_finished,
        )

        if not self.wait_until_finished and response.is_ok:
            return self._return_value('', exit_code=0)
        elif not response.is_ok:
            return self._return_value(response.body.strip(), response.is_ok)

        instance_id = response['counter']
        while not self._stages_finished(response):
            if self.verbose:
                print('.', end='')
            time.sleep(self._tick)
            response = self.pipeline.instance(instance_id)

        self._print_job_output(response)

        return self._return_value(
            False,
            self._run_successful(response),
        )

    def _convert_to_dict(self, args):
        # XXX: I would like to find a better way of dealing with this,
        # but I think I should instead focus on getting a better way of
        # parsing arguments altogether. And allow for it to be passed
        # multiple times there instead.
        if not args:
            return None

        variables = {}
        for arg in args.split(','):
            k, v = arg.split('=')
            variables[k] = v

        return variables

    def _stages_finished(self, response):
        for stage in response['stages']:
            if stage.get('result') not in self.pipeline.final_results:
                return False

        return True

    def _run_successful(self, response):
        for stage in response['stages']:
            if stage['result'] == 'Failed':
                return False

        return True

    def _print_job_output(self, instance):
        for metadata, output in self.pipeline.console_output(instance):
            job_masthead = ', '.join(('{0}="{1}"'.format(k, v) for k, v in metadata.items()))
            print('\n\n=== {0} ===\n\n'.format(job_masthead))
            print(output.strip())


class Unlock(BaseCommand):
    usage = ' '
    usage_summary = 'Unlocks the named pipeline if it\'s currently locked'

    def __init__(self, server, name):
        self.pipeline = server.pipeline(name)

    def run(self):
        return unlock_pipeline(self.pipeline)


class Pause(BaseCommand):
    usage = ' '
    usage_summary = 'Pauses the named pipeline'

    def __init__(self, server, name):
        self.pipeline = server.pipeline(name)

    def run(self):
        response = self.pipeline.status()

        if response and not response['paused']:
            return self.pipeline.pause()
        else:
            return False


class Unpause(BaseCommand):
    usage = ' '
    usage_summary = 'Unpauses the named pipeline'

    def __init__(self, server, name):
        self.pipeline = server.pipeline(name)

    def run(self):
        response = self.pipeline.status()

        if response and response['paused']:
            return self.pipeline.unpause()
        else:
            return False


class CheckAll(BaseCommand):
    usage = """
    Checks that all pipelines except those explicitly ignored are green
    and not stalled.

    Configuration is done in by the check_all section of the
    gocd-cli.cfg.

    For usage of the flags and return statuses see the check command.
    """
    usage_summary = 'Checks all pipelines to be green/non-stalled'

    exit_code = 0
    error_messages = []

    OK_STATUS = 0
    PAUSED_STATUS = 3

    def __init__(self, server, warn_run_time=30, crit_run_time=60, skip_paused=True):
        self.config = get_settings('check_all')
        self.server = server
        self.crit_run_time = crit_run_time
        self.warn_run_time = warn_run_time
        self.skip_paused = skip_paused

    def run(self):
        ignored_pipelines = (self.config.get('ignored_pipelines') or '').split(',')
        for pipeline in self.server.pipeline_groups().pipelines:
            if pipeline in ignored_pipelines:
                continue

            response = Check(
                self.server,
                pipeline,
                warn_run_time=self.warn_run_time,
                crit_run_time=self.crit_run_time,
            ).run()
            if response['exit_code'] != self.OK_STATUS:
                if self.skip_paused and response['exit_code'] == self.PAUSED_STATUS:
                    continue

                if(response['exit_code'] != self.PAUSED_STATUS
                   and response['exit_code'] > self.exit_code):
                    self.exit_code = response['exit_code']

                self.error_messages.append(response['output'])

        if self.exit_code != self.OK_STATUS:
            return self._return_value('\n'.join(self.error_messages), self.exit_code)
        else:
            return self._return_value('OK: All green', self.OK_STATUS)


class List(BaseCommand):
    usage = ' '
    usage_summary = 'Lists all pipelines with their current status'

    def __init__(self, server):
        self.server = server

    def run(self):
        for pipeline in self.server.pipeline_groups().pipelines:
            status = self.server.pipeline(pipeline).status()
            if not status:
                print('Error getting status for "{0}"'.format(pipeline))
                exit(3)

            print('{0}: {1}'.format(pipeline, self._format_status(status.payload)))

    def _format_status(self, status):
        return ', '.join(('{0}={1}'.format(k, v) for k, v in status.items()))
