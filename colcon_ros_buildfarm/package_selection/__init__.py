# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import traceback

from colcon_core.package_selection \
    import get_package_selection_extensions \
    as get_core_package_selection_extensions
from colcon_core.package_selection import logger
from colcon_core.plugin_system import instantiate_extensions
from colcon_core.plugin_system import order_extensions_by_priority


def get_package_selection_extensions():
    """
    Get the available package selection extensions.

    The extensions are ordered by their entry point name.

    :rtype: OrderedDict
    """
    extensions = instantiate_extensions(__name__)
    for name, extension in extensions.items():
        extension.PACKAGE_SELECTION_NAME = name
    return order_extensions_by_priority(extensions)


def get_all_package_selection_extensions():
    """
    Get the core and buildfarm-specific package selection extensions.

    The extensions are ordered by their entry point name.

    :rtype: OrderedDict
    """
    extensions = get_core_package_selection_extensions()
    extensions.update(get_package_selection_extensions())
    return order_extensions_by_priority(extensions)


def add_package_selection_arguments(parser):
    """
    Add the command line arguments for the package selection extensions.

    :param parser: The argument parser
    """
    package_selection_extensions = get_all_package_selection_extensions()
    group = parser.add_argument_group(title='Package selection arguments')
    for extension in package_selection_extensions.values():
        try:
            retval = extension.add_arguments(parser=group)
            assert retval is None, 'add_arguments() should return None'
        except Exception as e:  # noqa: F841
            # catch exceptions raised in package selection extension
            exc = traceback.format_exc()
            logger.error(
                'Exception in package selection extension '
                "'{extension.PACKAGE_SELECTION_NAME}': {e}\n{exc}"
                .format_map(locals()))
            # skip failing extension, continue with next one


def select_package_decorators(args, decorators):
    """
    Select the package decorators based on the command line arguments.

    The `selected` attribute of each decorator is updated by this function.

    :param args: The parsed command line arguments
    :param list decorators: The package decorators in topological order
    """
    # filtering must happen after the topological ordering since otherwise
    # packages in the middle of the dependency graph might be missing
    package_selection_extensions = get_all_package_selection_extensions()
    for extension in package_selection_extensions.values():
        try:
            retval = extension.select_packages(
                args=args, decorators=decorators)
            assert retval is None, 'select_packages() should return None'
        except Exception as e:  # noqa: F841
            # catch exceptions raised in package selection extension
            exc = traceback.format_exc()
            logger.error(
                'Exception in package selection extension '
                "'{extension.PACKAGE_SELECTION_NAME}': {e}\n{exc}"
                .format_map(locals()))
            # skip failing extension, continue with next one
