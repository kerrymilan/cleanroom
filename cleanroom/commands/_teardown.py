"""_teardown command.

@author: Tobias Hunger <tobias.hunger@gmail.com>
"""

import cleanroom.command as cmd
import cleanroom.context as context

import os.path


class _TeardownCommand(cmd.Command):
    """The _teardown Command."""

    def __init__(self):
        """Constructor."""
        super().__init__("_teardown",
                         "Implicitly run after any other command of a "
                         "system is run.")

    def __call__(self, file_name, line_number, run_context, *args, **kwargs):
        """Execute command."""
        run_context.run_hooks('_teardown')
        run_context.run_hooks('testing')

        run_context.pickle()

        self._unmount_system_directory(run_context)
        self._store_to_ostree(run_context)

    def _unmount_system_directory(self, run_context):
        """Unmount system directory."""
        if os.path.isdir(run_context.checkout_directory()):
            run_context.run('/usr/bin/umount', run_context.system_directory())

    def _store_to_ostree(self, run_context):
        run_context.ctx.printer.debug('Storing results in ostree.')
        ostree = run_context.ctx.binary(context.Binaries.OSTREE)

        to_commit = run_context.system_directory()
        if os.path.isdir(run_context.checkout_directory()):
            to_commit = run_context.checkout_directory()

        run_context.run(ostree,
                        '--repo={}'
                        .format(run_context.ctx.work_repository_directory()),
                        'commit',
                        '--branch', run_context.system,
                        '--subject', run_context.timestamp,
                        '--add-metadata-string="timestamp={}"'
                        .format(run_context.timestamp),
                        outside=True, work_directory=to_commit)
