# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

import re
import subprocess

from colcon_core.plugin_system import satisfies_version
from colcon_core.subprocess import run
from colcon_ros_buildfarm.package_repository.local import \
    LocalPackageRepositoryExtensionPoint
from colcon_ros_buildfarm.package_repository.local import logger


class LocalRpmPackageRepository(LocalPackageRepositoryExtensionPoint):
    """Import package into a local RPM package repository."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            LocalPackageRepositoryExtensionPoint.EXTENSION_POINT_VERSION,
            '^1.0')
        self._pkg_match = re.compile(
            r'(.+)-(\d+(?:\.\d+)*)-(\d+.*)\.([^\.]+)\.rpm')

    def initialize(  # noqa: D102
        self, base_path, os_name, os_code_name, arch
    ):
        srpms_dir = base_path / os_name / os_code_name / 'SRPMS'
        arch_dir = base_path / os_name / os_code_name / arch
        debug_dir = arch_dir / 'debug'

        for repo_dir in (srpms_dir, arch_dir, debug_dir):
            if (repo_dir / 'repodata' / 'repomd.xml').is_file():
                continue
            repo_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                'Initializing RPM metadata in {repo_dir}'.format_map(locals()))
            subprocess.check_call(
                ['createrepo_c', '--no-database', str(repo_dir)])

    async def import_source(  # noqa: D102
        self, base_path, os_name, os_code_name, artifact_path
    ):
        srpms_dir = base_path / os_name / os_code_name / 'SRPMS'
        srpms = set(artifact_path.glob('sourcepkg/*.src.rpm'))
        num_srpms = len(srpms)
        if num_srpms != 1:
            logger.warning(
                'Found unexpected number of source RPMs in '
                '{artifact_path} ({num_srpms})'.format_map(locals()))
        if srpms:
            await self._import_to(srpms_dir, srpms)

    async def import_binary(  # noqa: D102
        self, base_path, os_name, os_code_name, arch, artifact_path
    ):
        arch_dir = base_path / os_name / os_code_name / arch
        debug_dir = arch_dir / 'debug'

        srpms = set(artifact_path.glob('binarypkg/*.src.rpm'))
        debug_rpms = set(artifact_path.glob('binarypkg/*-debuginfo-*.rpm'))
        debug_rpms.update(artifact_path.glob('binarypkg/*-debugsource-*.rpm'))
        arch_rpms = set(artifact_path.glob('binarypkg/*.rpm'))
        arch_rpms.difference_update(srpms)
        arch_rpms.difference_update(debug_rpms)

        if arch_rpms:
            await self._import_to(arch_dir, arch_rpms)
        else:
            logger.warning(
                'Found no arch RPMs to import '
                'from {artifact_path}'.format_map(locals()))

        if debug_rpms:
            await self._import_to(debug_dir, debug_rpms)

    async def _import_to(self, repo_dir, rpms):
        logger.debug(
            'Importing the following RPMs into {}: {}'.format(
                repo_dir, ', '.join(rpm.name for rpm in rpms)))

        # TODO(cottsay): More invalidation

        names = set()
        for rpm in rpms:
            m = self._pkg_match.match(rpm.name)
            if not m:
                logger.warning(
                    'Failed to parse package name: {rpm.name}'.format_map(
                        locals()))
                continue
            names.add(m.group(1))

        for in_repo in repo_dir.glob('*.rpm'):
            m = self._pkg_match.match(in_repo.name)
            if m and m.group(1) in names:
                in_repo.unlink()

        for rpm in rpms:
            in_repo = repo_dir / rpm.name
            # TODO(cottsay): Fall back to copy
            in_repo.hardlink_to(rpm)

        res = await run(
            [
                'createrepo_c', '--update', '--no-database',
                '--excludes=debug/*', str(repo_dir)],
            None, None)
        res.check_returncode()
