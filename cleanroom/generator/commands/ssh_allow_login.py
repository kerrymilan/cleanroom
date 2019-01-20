# -*- coding: utf-8 -*-
"""ssh_allow_login command.

@author: Tobias Hunger <tobias.hunger@gmail.com>
"""


from cleanroom.generator.command import Command
from cleanroom.generator.helper.generic.file import (chmod, chown, exists, isdir, read_file,)
from cleanroom.generator.helper.generic.user import user_data

from cleanroom.exceptions import GenerateError
from cleanroom.printer import info, trace

import os.path


class SshAllowLoginCommand(Command):
    """The ssh_allow_login command."""

    def __init__(self):
        """Constructor."""
        super().__init__('ssh_allow_login', syntax='<USER> <PUBLIC_KEYFILE> '
                         'options=<OPTIONS>',
                         help='Authorize <PUBLIC_KEYFILE> to log in '
                         'as <USER>.', file=__file__)

    def validate_arguments(self, location, *args, **kwargs):
        """Validate the arguments."""
        self._validate_args_exact(location, 2, '"{}" needs a user and '
                                  'a public keyfile.', *args)
        self._validate_kwargs(location, ('options'), **kwargs)

    def _check_or_create_directory(self, location, system_context, dir,
                                   **kwargs):
        if not exists(system_context, dir):
            system_context.execute(location.next_line(), 'mkdir', dir, **kwargs)
            return
        if not isdir(system_context, dir):
            raise GenerateError('"{}" needs directory "{}", but that exists and '
                                'is not a directory.'.format(self.name(), dir),
                                location=location)

    def __call__(self, location, system_context, *args, **kwargs):
        """Execute command."""
        user = args[0]
        keyfile = args[1]

        info('Adding ssh key to {}\'s authorized_keys file.'.format(user))
        data = user_data(system_context, user)
        if data is None:
            raise GenerateError('"{}" could not find user "{}".'
                                .format(self.name(), user),
                                location=location)

        trace('{} mapping: UID {}, GID {}, home: {}.'
              .format(user, data.uid, data.gid, data.home))
        self._check_or_create_directory(location, system_context, data.home,
                                        mode=0o750, user=data.uid,
                                        group=data.gid)
        ssh_directory = os.path.join(data.home, '.ssh')
        self._check_or_create_directory(location, system_context, ssh_directory,
                                        mode=0o700, user=data.uid,
                                        group=data.gid)

        key = read_file(system_context, keyfile, outside=True).decode('utf-8')

        authorized_file = os.path.join(ssh_directory, 'authorized_keys')
        line = ''

        options = kwargs.get('options', '')

        if options:
            line = options + ' ' + key + '\n'
        else:
            line += key + '\n'

        system_context.execute(location.next_line(), 'append', authorized_file, line,
                               force=True)
        chown(system_context, data.uid, data.gid, authorized_file)
        chmod(system_context, 0o600, authorized_file)
