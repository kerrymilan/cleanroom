#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The class that holds context data for the executor.

@author: Tobias Hunger <tobias.hunger@gmail.com>
"""


import cleanroom.command as command
import cleanroom.helper.generic.run as run
import cleanroom.helper.generic.file as file
import cleanroom.parser as parser

import datetime
import os
import os.path
import pickle
import string


class _RunContextPickler(pickle.Pickler):
    """Pickler for the RunContext."""

    def persistent_id(self, obj):
        """Treat commands special when pickling."""
        if isinstance(obj, command.Command):
            return ('Command', obj.name())
        return None


class _RunContextUnpickler(pickle.Unpickler):
    """Unpickler for the RunContext."""

    def persistent_load(self, pid):
        tag, cmd = pid

        if tag == 'Command':
            return parser.Parser.command(cmd)
        else:
            raise pickle.UnpicklingError('Unsupported persistent object.')


class RunContext:
    """Context data for the execution os commands."""

    def __init__(self, ctx, *, system,
                 timestamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')):
        """Constructor."""
        self.ctx = ctx
        self.system = system
        self.base_system = None
        self.timestamp = timestamp
        self.base_context = None
        self.hooks = {}
        self.hooks_that_already_ran = []
        self.substitutions = {}
        self.local_substitutions = {}
        self.flags = {}
        self.reset_command()

        self._command = None

        self._setup_substitutions()

        assert(self.ctx)
        assert(self.system)

    def _setup_substitutions(self):
        self.set_substitution('TIMESTAMP', self.timestamp)
        self.set_substitution('SYSTEM', self.system, local=True)
        self.set_substitution('ROOT', self.fs_directory(), local=True)
        self.set_substitution('BASE_SYSTEM', '', local=True)

    @staticmethod
    def _storage_directory(ctx, system):
        """Find base directory for all temporary system files."""
        return os.path.join(ctx.work_directory(), 'storage', system)

    def storage_directory(self, system=None):
        """Location of temporary system files."""
        if system is None:
            system = self.system
        return self.ctx.storage_directory(system)

    def current_system_directory(self):
        """Location of the current system installation."""
        return self.ctx.current_system_directory()

    def fs_directory(self, system=None):
        """Location of the systems filesystem root."""
        return self.ctx.fs_directory(system)

    def meta_directory(self, system=None):
        """Location of the systems meta-data directory."""
        return self.ctx.meta_directory(system)

    def expand_files(self, *files):
        """Map and expand files from inside to outside paths."""
        return file.expand_files(self, *files)

    def file_name(self, path):
        """Map a file from inside to outside path."""
        if not os.path.isabs(path):
            return path
        return file.file_name(self, path)

    def _install_base_context(self, base_context):
        """Set up base context."""
        self.base_context = base_context
        self.timestamp = base_context.timestamp
        self.hooks = base_context.hooks
        self.substitutions = base_context.substitutions
        self.flags = base_context.flags

        self._setup_substitutions()  # Override critical substitutions again:-)

    def system_definition_directory(self):
        """Return the top level system definition directory of a system."""
        return self.ctx.system_definition_directory(self.system)

    def set_command(self, command_name, *,
                    file_name, line_number, line_offset):
        """Set the current command."""
        assert(self._command is None)
        self._command = command_name
        self.file_name = file_name
        self.line_number = line_number
        self.line_offset = line_offset

    def reset_command(self):
        """Reset the current command."""
        self._command = None
        self._line_number = -1
        self._line_offset = -1

    def _add_hook(self, hook, exec_object):
        """Add a hook."""
        self.ctx.printer.info('Adding hook "{}": {}.'
                              .format(hook, exec_object))
        self.hooks.setdefault(hook, []).append(exec_object)
        self.ctx.printer.trace('Hook {} has {} entries.'
                               .format(hook, len(self.hooks[hook])))

    def add_hook(self, hook, command, *args,
                 message='<unknown hook>', **kwargs):
        """Add a hook."""
        self._add_hook(hook, parser.Parser.create_execute_object(
            self.file_name, self.line_number, self.line_offset,
            command, *args, message=message, **kwargs))

    def run_hooks(self, hook):
        """Run all the registered hooks."""
        if hook in self.hooks_that_already_ran:
            self.ctx.printer.trace('Skipping hooks "{}": Already ran them.'
                                   .format(hook))
            return

        command_list = self.hooks.setdefault(hook, [])
        self.ctx.printer.trace('Runnnig hook {} with {} entries.'
                               .format(hook, len(command_list)))
        if not command_list:
            return

        self.ctx.printer.h3('Running {} hooks.'.format(hook), verbosity=1)
        for cmd in command_list:
            os.chdir(self.ctx.systems_directory())
            cmd.execute(self)

        self.hooks_that_already_ran.append(hook)

    def set_substitution(self, key, value, local=False):
        """Add a substitution to the substitution table."""
        if local:
            self.local_substitutions[key] = value
        else:
            self.substitutions[key] = value

    def substitution(self, key):
        """Get substitution value."""
        return self.local_substitutions.get(key,
                                            self.substitutions.get(key, None))

    def has_substitution(self, key):
        """Check wether a substitution is defined."""
        return key in self.local_substitutions or key in self.substitutions

    def substitute(self, text):
        """Substitute variables in text."""
        template = string.Template(text)
        all_substitutions = {**self.substitutions, **self.local_substitutions}
        return template.substitute(all_substitutions)

    def run(self, *args, outside=False, **kwargs):
        """Run a command in this run_context."""
        assert('chroot' not in kwargs)

        if not outside:
            kwargs['chroot'] = self.fs_directory()

        return run.run(*args, trace_output=self.ctx.printer.trace, **kwargs)

    def pickle(self):
        """Pickle this run_context."""
        ctx = self.ctx

        pickle_jar = ctx.pickle_jar()
        hooks_that_ran = self.hooks_that_already_ran

        ctx.printer.debug('Pickling run_context into {}.'.format(pickle_jar))
        self.ctx = None  # Disconnect context for the pickling!
        self.hooks_that_already_ran = []

        with open(pickle_jar, 'wb') as jar:
            _RunContextPickler(jar).dump(self)

        # Restore state that should not get saved:
        self.ctx = ctx
        self.hooks_that_already_ran = hooks_that_ran

    def unpickle_base_context(self, system):
        """Create a new run_context by unpickling a file."""
        pickle_jar = self.ctx.pickle_jar(system)

        self.ctx.printer.debug('Unpickling base run_context from {}.'
                               .format(pickle_jar))
        with open(pickle_jar, 'rb') as jar:
            base_context = _RunContextUnpickler(jar).load()
        self._install_base_context(base_context)

    def execute(self, command, *args, **kwargs):
        """Execute a command."""
        cmd = parser.Parser.command(command)
        dependency = cmd.validate_arguments(self, *args, **kwargs)
        assert(dependency is None)
        cmd(self, *args, **kwargs)


if __name__ == '__main__':
    pass
