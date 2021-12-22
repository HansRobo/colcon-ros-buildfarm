# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

import logging

from catkin_pkg.package import InvalidPackage
from catkin_pkg.package import parse_package_string
from colcon_core.dependency_descriptor import DependencyDescriptor
from colcon_core.logging import colcon_logger
from colcon_core.package_descriptor import PackageDescriptor
from colcon_core.plugin_system import satisfies_version
from colcon_ros_buildfarm.package_discovery import \
    BuildfarmPackageDiscoveryExtensionPoint
from ros_buildfarm.common import filter_buildfile_packages_recursively
from ros_buildfarm.common import get_package_condition_context
from ros_buildfarm.config import get_index as get_config_index
from ros_buildfarm.config import get_release_build_files
from rosdistro import get_cached_distribution
from rosdistro import get_index


logger = colcon_logger.getChild(__name__)


def _get_effective_log_level():
    for handler in colcon_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            return handler.level
    return logging.INFO


def discover_packages_from_distro(distro, condition_context):
    """
    Discover packages available for a specific ROS distribution.

    :param distro: The cached ROS distribution
    :param condition_context: The context for evaluating package dependency
      conditionals
    """
    descs = set()
    for pkg_name in distro.release_packages.keys():
        desc = PackageDescriptor(distro.name)
        desc.name = pkg_name
        desc.type = 'ros_buildfarm.release'
        pkg_xml = distro.get_release_package_xml(pkg_name)
        try:
            pkg = parse_package_string(pkg_xml)
        except InvalidPackage as e:
            logger.error(
                f"Failed to parse manifest for package '{pkg_name}': {e}")
            continue
        else:
            pkg.evaluate_conditions(condition_context)

        # get dependencies
        for d in pkg.build_depends + pkg.buildtool_depends:
            assert d.evaluated_condition is not None
            if d.evaluated_condition:
                desc.dependencies['build'].add(DependencyDescriptor(
                    d.name, metadata=_create_metadata(d)))

        for d in (
            pkg.build_export_depends +
            pkg.buildtool_export_depends +
            pkg.exec_depends
        ):
            assert d.evaluated_condition is not None
            if d.evaluated_condition:
                desc.dependencies['run'].add(DependencyDescriptor(
                    d.name, metadata=_create_metadata(d)))

        for d in pkg.test_depends:
            assert d.evaluated_condition is not None
            if d.evaluated_condition:
                desc.dependencies['test'].add(DependencyDescriptor(
                    d.name, metadata=_create_metadata(d)))

        desc.metadata['maintainers'] = [
            str(m) for m in pkg.maintainers if m.email]

        descs.add(desc)

    return descs


def discover_packages_from_config(config_url, ros_distro, build_name=None):
    """
    Discover packages available to build for a specific ROS buildfarm config.

    :param config_url: ROS buildfarm configuration index URL
    :param ros_distro: Name of the ROS distribution
    :param build_name: Name of the release build configuration
    """
    if build_name is None:
        build_name = 'default'

    config = get_config_index(config_url)
    build_files = get_release_build_files(config, ros_distro)
    build_file = build_files[build_name]

    target_platforms = set()
    for os_name, os_code_names in build_file.targets.items():
        for os_code_name, arches in os_code_names.items():
            for arch in arches:
                target_platforms.add((os_name, os_code_name, arch))

    index = get_index(config.rosdistro_index_url)
    distro = get_cached_distribution(index, ros_distro)
    condition_context = get_package_condition_context(index, distro.name)
    descs = discover_packages_from_distro(distro, condition_context)

    for d in descs:
        d.metadata.setdefault('notify_emails', [])
        if build_file.notify_maintainers:
            d.metadata['notify_emails'] += d.metadata.get('maintainers', [])
        d.metadata['notify_emails'] += build_file.notify_emails
        d.metadata['target_platforms'] = target_platforms

    all_pkg_names = {d.name for d in descs}
    pkg_names = filter_buildfile_packages_recursively(
        all_pkg_names, build_file, distro)

    return {d for d in descs if d.name in pkg_names}


class ConfigPackageDiscovery(BuildfarmPackageDiscoveryExtensionPoint):
    """Discover packages which are part of a ROS buildfarm configuration."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            BuildfarmPackageDiscoveryExtensionPoint.EXTENSION_POINT_VERSION,
            '^1.0')

    def add_arguments(  # noqa: D102
        self, *, parser, with_default, single_path=False
    ):
        parser.add_argument(
            '--from-upstream',
            action='store_true',
            help='Build packages which are defined in the upstream ROS '
                 'distribution')

    def has_parameters(self, *, args):  # noqa: D102
        return (
            hasattr(args, 'config_url') and
            hasattr(args, 'ros_distro') and
            hasattr(args, 'build_name') and
            args.from_upstream)

    def discover(self, *, args, identification_extensions):  # noqa: D102
        log_level = _get_effective_log_level()
        logging.getLogger('rosdistro').setLevel(log_level)
        logging.getLogger('ros_buildfarm').setLevel(log_level)

        return discover_packages_from_config(
            args.config_url, args.ros_distro, args.build_name)


def _create_metadata(dependency):
    metadata = {}
    attributes = (
        'version_lte',
        'version_lt',
        'version_gte',
        'version_gt',
        'version_eq',
    )
    for attr in attributes:
        if getattr(dependency, attr, None) is not None:
            metadata[attr] = getattr(dependency, attr)
    return metadata
