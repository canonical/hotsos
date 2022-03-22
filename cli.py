#!/usr/bin/python3
import click
import os
import sys
import yaml

from core.log import setup_logging, log
from core import output_filter
from core.cli_helpers import CLIHelper


if __name__ == '__main__':
    @click.command()
    @click.option('--agent-error-key-by-time', default=False, is_flag=True)
    @click.option('--full-mode-explicit', default=False, is_flag=True)
    @click.option('--minimal-mode', default=None)
    @click.option('--user-summary', default=False, is_flag=True)
    @click.option('--html-escape', default=False, is_flag=True)
    @click.option('--format', default='yaml')
    @click.option('--save', default=False, is_flag=True)
    @click.option('--debug', default=False, is_flag=True)
    @click.option('--all-logs', default=False, is_flag=True,
                  help=("use the full history of logrotated logs as "
                        "opposed to just the most recent"))
    @click.option('--plugin', multiple=True)
    @click.option('--defs-path')
    @click.option('--data-root')
    def cli(data_root, defs_path, plugin, all_logs, debug, save, format,
            html_escape, user_summary, minimal_mode, full_mode_explicit,
            agent_error_key_by_time):

        # TODO - move away from using environment variables to pass this
        #        information around.
        # root of all data which will be either host / or sosreport root.
        os.environ['DATA_ROOT'] = data_root
        os.environ['USE_ALL_LOGS'] = str(all_logs)
        os.environ['AGENT_ERROR_KEY_BY_TIME'] = str(agent_error_key_by_time)
        os.environ['PLUGIN_YAML_DEFS'] = defs_path

        # IMPORTANT: must be import after env vars set
        from client import HotSOSClient  # pylint: disable=C0415

        if debug:
            setup_logging(debug)

        if user_summary:
            log.debug("User summary provided in %s", data_root)
            with open(data_root) as fd:
                summary_yaml = yaml.safe_load(fd)
        else:
            summary_yaml = HotSOSClient().run('hotsos')
            for _plugin in plugin:
                _output = HotSOSClient().run(_plugin)
                if _output:
                    summary_yaml.update(_output)

        formatted = output_filter.apply_output_formatting(summary_yaml,
                                                          format, html_escape,
                                                          minimal_mode)
        if save:
            if user_summary:
                output_name = os.path.basename(user_summary)
                output_name = output_name.rpartition('.')[0]
            else:
                if data_root != '/':
                    output_name = os.path.basename(data_root)
                else:
                    output_name = "hotsos-{}".format(CLIHelper().hostname())

            if minimal_mode:
                if formatted:
                    out = "{}.short.summary".format(output_name)
                    with open(out, 'w', encoding='utf-8') as fd:
                        fd.write(formatted)
                        fd.write('\n')

                    sys.stdout.write("INFO: short summary written to {}\n".
                                     format(out))
                if full_mode_explicit:
                    formatted = output_filter.apply_output_formatting(
                                                          summary_yaml, format,
                                                          html_escape)

            if not minimal_mode or full_mode_explicit:
                if formatted:
                    out = "{}.summary".format(output_name)
                    with open(out, 'w', encoding='utf-8') as fd:
                        fd.write(formatted)
                        fd.write('\n')

                    sys.stdout.write("INFO: full summary written to {}\n".
                                     format(out))

        else:
            if debug:
                sys.stderr.write('Results:\n')

            if formatted:
                sys.stdout.write(formatted)

    cli()
