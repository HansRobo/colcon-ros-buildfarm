# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

from colcon_core.package_discovery import PackageDiscoveryExtensionPoint
from colcon_core.plugin_system import instantiate_extensions
from colcon_core.plugin_system import order_extensions_by_priority


class BuildfarmPackageDiscoveryExtensionPoint(PackageDiscoveryExtensionPoint):
    """
    The interface for buildfarm package discovery extensions.

    This interface specifically discovers buildable packages, not packages
    which are available for installation.
    """

    pass


def get_package_discovery_extensions():
    """
    Get the available buildfarm package discovery extensions.

    The extensions are ordered by their priority and entry point name.

    :rtype: OrderedDict
    """
    extensions = instantiate_extensions(__name__)
    for name, extension in extensions.items():
        extension.PACKAGE_DISCOVERY_NAME = name
    return order_extensions_by_priority(extensions)
