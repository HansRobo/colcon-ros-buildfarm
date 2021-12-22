# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

import os
from pathlib import Path

from colcon_core.event_handler import EventHandlerExtensionPoint
from colcon_core.event_reactor import EventReactorShutdown
from colcon_core.plugin_system import instantiate_extensions
from colcon_core.plugin_system import satisfies_version
from colcon_ros_buildfarm.config_augmentation \
    import ConfigAugmentationExtensionPoint
from colcon_ros_buildfarm.package_repository import logger
from colcon_ros_buildfarm.package_repository \
    import PackageRepositoryExtensionPoint
from colcon_ros_buildfarm.package_repository.local.server \
    import SimpleFileServer
import yaml


class LocalPackageRepositoryExtensionPoint:
    """
    The interface for 'local' package repository importers.

    Each extension is expected to handle a specific package format.
    """

    """The version of the executor extension interface."""
    EXTENSION_POINT_VERSION = '1.0'

    def initialize(self, base_path, os_name, os_code_name, arch):
        """
        Initialize the local repository metadata (if necessary).

        :param base_path: The base path of the repository to import into
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param arch: The system architecture the package was built for
        """
        pass

    async def import_source(
        self, base_path, os_name, os_code_name, artifact_path
    ):
        """
        Import a source package into the local repository.

        :param base_path: The base path of the repository to import into
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param artifact_path: The path to the package artifact(s) to be
          imported
        """
        raise NotImplementedError()

    async def import_binary(
        self, base_path, os_name, os_code_name, arch, artifact_path
    ):
        """
        Import a binary package into the repository.

        :param base_path: The base path of the repository to import into
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param arch: The system architecture the package was built for
        :param artifact_path: The path to the package artifact(s) to be
          imported
        """
        raise NotImplementedError()


class LocalPackageRepository(
    ConfigAugmentationExtensionPoint,
    EventHandlerExtensionPoint,
    PackageRepositoryExtensionPoint,
):
    """Import packages into a repository residing on disk."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ConfigAugmentationExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        satisfies_version(
            EventHandlerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        satisfies_version(
            PackageRepositoryExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self._server = None

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--repo-base',
            default='repo',
            help='The base path for locally importing built packages '
                 '(default: repo)')

    async def import_source(  # noqa: D102
        self, args, os_name, os_code_name, artifact_path
    ):
        repo_base = Path(os.path.abspath(args.repo_base))
        extension = get_local_package_repository_extension_for_os(os_name)
        if not extension:
            logger.warn(
                'No local package repository extension found to import source '
                "package for OS '{os_name}'".format_map(locals()))
            return
        return await extension.import_source(repo_base, os_name,
                                             os_code_name, artifact_path)

    async def import_binary(  # noqa: D102
        self, args, os_name, os_code_name, arch, artifact_path
    ):
        repo_base = Path(os.path.abspath(args.repo_base))
        extension = get_local_package_repository_extension_for_os(os_name)
        if not extension:
            logger.warn(
                'No local package repository extension found to import binary '
                "package for OS '{os_name}'".format_map(locals()))
            return
        return await extension.import_binary(repo_base, os_name, os_code_name,
                                             arch, artifact_path)

    def __call__(self, event):  # noqa: D102
        if isinstance(event[0], EventReactorShutdown) and self._server:
            self._server.stop()
            self._server = None

    def augment_config(self, config_path, args):  # noqa: D102
        package_repository = getattr(args, 'package_repository', None)
        if package_repository != 'local':
            return

        repo_base = Path(args.repo_base).resolve()
        repo_base.mkdir(parents=True, exist_ok=True)

        index_path = config_path / 'index.yaml'
        with index_path.open('r') as f:
            index_data = yaml.safe_load(f)

        ros_distro_data = index_data['distributions'][args.ros_distro]
        build_file_path = ros_distro_data['release_builds'][args.build_name]
        build_file_path = config_path / build_file_path

        with build_file_path.open('r') as f:
            build_file_data = yaml.safe_load(f)

        targets = set()
        for os_name, os_code_names in build_file_data['targets'].items():
            for os_code_name, arches in os_code_names.items():
                for arch in arches:
                    targets.add((os_name, os_code_name, arch))

        for os_name, os_code_name, arch in targets:
            extension = get_local_package_repository_extension_for_os(os_name)
            if not extension:
                logger.warning(
                    f'No repository extension for {os_name} - '
                    'disabling local repo')
                return
            extension.initialize(repo_base, os_name, os_code_name, arch)

        # This appears to be a general limitation of ros_buildfarm build files
        os_names = {target[0] for target in targets}
        assert len(os_names) == 1, 'A build file can support only a single OS'
        os_name = next(iter(os_names))

        self._server = SimpleFileServer(str(repo_base))
        host, port = self._server.start()

        if not build_file_data['repositories'].get('keys'):
            build_file_data['repositories']['keys'] = []
        if not build_file_data['repositories'].get('urls'):
            build_file_data['repositories']['urls'] = []

        repo_url = 'http://{host}:{port}/{os_name}'.format_map(locals())
        build_file_data['repositories']['keys'].insert(0, '')
        if os_name in ('rhel', 'fedora'):
            # TODO(cottsay): Make it so ros_buildfarm can handle this
            build_file_data['repositories']['urls'].insert(
                0, repo_url + '/$releasever/$basearch/')
        else:
            build_file_data['repositories']['urls'].insert(0, repo_url)
        build_file_data['target_repository'] = repo_url

        with build_file_path.open('w') as f:
            yaml.dump(build_file_data, f)


def get_local_package_repository_extension_for_os(os_name):
    """
    Get the appropriate local package repository extension an operating system.

    :param os_name: Name of the operating system
    """
    from ros_buildfarm.common import package_format_mapping

    package_format = package_format_mapping.get(os_name)
    if not package_format:
        return None
    extensions = instantiate_extensions(__name__)
    return extensions.get(package_format)
