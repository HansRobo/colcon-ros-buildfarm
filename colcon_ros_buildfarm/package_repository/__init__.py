# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

import os
import traceback

from colcon_core.environment_variable import EnvironmentVariable
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import get_first_line_doc
from colcon_core.plugin_system import instantiate_extensions
from colcon_core.plugin_system import order_extensions_by_name

logger = colcon_logger.getChild(__name__)

"""Environment variable to override the default package repository"""
DEFAULT_PACKAGE_REPOSITORY_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'COLCON_DEFAULT_PACKAGE_REPOSITORY',
    'Select the default package repository extension')


class PackageRepositoryExtensionPoint:
    """
    The interface for package repository extensions.

    A package repository extension provides a mechanism for manipulating a
    system package repository's contents.
    """

    """The version of the package repository extension interface."""
    EXTENSION_POINT_VERSION = '1.0'

    def add_arguments(self, *, parser):
        """
        Add command line arguments specific to the package repository.

        The method is intended to be overridden in a subclass.

        :param parser: The argument parser
        """
        pass

    async def import_source(
        self, args, os_name, os_code_name, artifact_path
    ):
        """
        Import a source package into the repository.

        :param args: The parsed command line arguments
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param artifact_path: The path to the package artifact(s) to be
          imported
        """
        raise NotImplementedError()

    async def import_binary(
        self, args, os_name, os_code_name, arch, artifact_path
    ):
        """
        Import a binary package into the repository.

        :param args: The parsed command line arguments
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param arch: The system architecture the package was built for
        :param artifact_path: The path to the package artifact(s) to be
          imported
        """
        raise NotImplementedError()


def get_package_repository_extensions():
    """
    Get the available package repository extensions.

    The extensions are ordered by their entry point name.

    :rtype: OrderedDict
    """
    extensions = instantiate_extensions(__name__)
    for name, extension in extensions.items():
        extension.PACKAGE_REPOSITORY_NAME = name
    return order_extensions_by_name(extensions)


def add_package_repository_arguments(parser):
    """
    Add the command line arguments for the package repository extensions.

    :param parser: The argument parser
    """
    group = parser.add_argument_group(title='Package repository arguments')
    extensions = get_package_repository_extensions()
    descriptions = ''
    for key, extension in extensions.items():
        desc = get_first_line_doc(extension)
        if not desc:
            # show extensions without a description
            # to mention the available options
            desc = '<no description>'
        # it requires a custom formatter to maintain the newline
        descriptions += '\n* {key}: {desc}'.format_map(locals())

    default = os.environ.get(
        DEFAULT_PACKAGE_REPOSITORY_ENVIRONMENT_VARIABLE.name)
    if default not in extensions:
        default = next(iter(extensions.keys()), None)

    group.add_argument(
        '--package-repository', type=str, choices=extensions.keys(),
        default=default,
        help='The repository extension to import processed packages (default: '
             '{default}){descriptions}'.format_map(locals()))

    for extension in extensions.values():
        try:
            retval = extension.add_arguments(parser=group)
            assert retval is None, 'add_arguments() should return None'
        except Exception as e:  # noqa: F841
            # catch exceptions raised in extension
            exc = traceback.format_exc()
            logger.error(
                'Exception in package repository extension '
                "'{extension.EXECUTOR_NAME}': {e}\n{exc}"
                .format_map(locals()))
            # skip failing extension, continue with next one


def get_package_repository_extension(args):
    """
    Get the package repository extension to use.

    :param args: The parsed command line arguments

    :returns: The package repository extension
    """
    extensions = get_package_repository_extensions()
    for key, extension in extensions.items():
        if key == args.package_repository:
            return extension
    # One package repository extension should always be selected by the default
    # value. In case there are no package repository extensions available the
    # add argument function should have already failed.
    assert False
