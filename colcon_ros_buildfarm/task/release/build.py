# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

import os
from pathlib import Path
import shutil

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from colcon_core.subprocess import run as colcon_core_subprocess_run
from colcon_core.task import run
from colcon_core.task import TaskExtensionPoint
from colcon_ros_buildfarm.package_repository import \
    get_package_repository_extension

logger = colcon_logger.getChild(__name__)


class BuildfarmReleaseBuildTask(TaskExtensionPoint):
    """Build ROS buildfarm release jobs."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(TaskExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    async def build(self):  # noqa: D102
        args = self.context.args
        pkg = self.context.pkg

        staging_dir = Path(args.build_base) / pkg.name
        repo_dir = staging_dir / 'ros_buildfarm'
        binary_dir = staging_dir / 'binary'
        source_dir = staging_dir / 'source'
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
        if binary_dir.exists():
            shutil.rmtree(binary_dir)
        if source_dir.exists():
            shutil.rmtree(source_dir)
        repo_dir.mkdir(parents=True)
        binary_dir.mkdir(parents=True)
        source_dir.mkdir(parents=True)

        self.progress('setup')
        ros_buildfarm_branch = getattr(args, 'ros_buildfarm_branch', 'master')
        clone_res = await run(self.context, [
            'git', 'clone', '--depth', '1', '-b', ros_buildfarm_branch, '-q',
            'https://github.com/ros-infrastructure/ros_buildfarm.git',
            str(repo_dir)])
        if clone_res.returncode:
            return clone_res.returncode
        (binary_dir / 'ros_buildfarm').symlink_to('../ros_buildfarm')
        (source_dir / 'ros_buildfarm').symlink_to('../ros_buildfarm')

        pythonpath = os.environ.get('PYTHONPATH', '')
        if pythonpath:
            pythonpath += ':'
        env = {
            **dict(os.environ),
            'PYTHONPATH': pythonpath + str(repo_dir.resolve()),
        }
        script_path = staging_dir / 'job.sh'
        generation_script_path = (
            repo_dir / 'scripts' / 'release' / 'generate_release_script.py')
        generation_cmd = [
            'python3', str(generation_script_path), args.config_url,
            args.ros_distro, args.build_name, pkg.name, args.os_name,
            args.os_code_name, args.arch]
        logger.debug('Invoking script generation command: {}'.format(
            ' '.join(generation_cmd)))
        with script_path.open('wb') as script_file:
            gen_res = await colcon_core_subprocess_run(
                generation_cmd,
                stdout_callback=script_file.write, stderr_callback=None,
                env=env)
        if gen_res.returncode:
            return gen_res.returncode

        self.progress('build')
        build_res = await run(
            self.context, ['sh', 'job.sh', '-y'], cwd=str(staging_dir))
        if build_res.returncode:
            return build_res.returncode

        # Import the built artifacts

        self.progress('import')
        extension = get_package_repository_extension(args)
        await extension.import_source(
            args, args.os_name, args.os_code_name, source_dir)
        await extension.import_binary(
            args, args.os_name, args.os_code_name, args.arch, binary_dir)
