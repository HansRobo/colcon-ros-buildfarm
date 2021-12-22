# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

from collections import OrderedDict
import os
from pathlib import Path

from colcon_core.dependency_descriptor import DependencyDescriptor
from colcon_core.event_handler import add_event_handler_arguments
from colcon_core.executor import add_executor_arguments
from colcon_core.executor import execute_jobs
from colcon_core.executor import Job
from colcon_core.logging import colcon_logger
from colcon_core.package_augmentation import augment_packages
from colcon_core.package_discovery import add_package_discovery_arguments
from colcon_core.package_discovery import discover_packages
from colcon_core.package_identification.ignore import IGNORE_MARKER
from colcon_core.plugin_system import satisfies_version
from colcon_core.task import add_task_arguments
from colcon_core.task import get_task_extension
from colcon_core.task import TaskContext
from colcon_core.topological_order import topological_order_packages
from colcon_core.verb import check_and_mark_build_tool
from colcon_core.verb import VerbExtensionPoint
from colcon_ros_buildfarm.config_augmentation import get_config
from colcon_ros_buildfarm.logging import configure_ros_buildfarm_logger
from colcon_ros_buildfarm.package_discovery \
    import get_package_discovery_extensions
from colcon_ros_buildfarm.package_repository \
    import add_package_repository_arguments
from colcon_ros_buildfarm.package_selection \
    import add_package_selection_arguments
from colcon_ros_buildfarm.package_selection \
    import select_package_decorators


DEFAULT_CONFIG_URL = 'https://raw.githubusercontent.com' \
    '/ros2/ros_buildfarm_config/ros2/index.yaml'

logger = colcon_logger.getChild(__name__)


def _discover_packages(args):
    extensions = get_package_discovery_extensions()
    descs = discover_packages(args, {}, discovery_extensions=extensions)

    # Inject ros_workspace dependency
    ros_workspace = next(
        iter(d for d in descs if d.name == 'ros_workspace'),
        None)
    if ros_workspace:
        workspace_deps = {
            ros_workspace.name,
            *ros_workspace.dependencies['build'],
        }
        for d in descs:
            if d.name in workspace_deps:
                continue
            d.dependencies['build'].add(DependencyDescriptor('ros_workspace'))
            d.dependencies['run'].add(DependencyDescriptor('ros_workspace'))

    return descs


def _get_packages(args):
    descriptors = _discover_packages(args)
    augment_packages(
        descriptors, additional_argument_names=['*'])
    decorators = topological_order_packages(
        descriptors,
        recursive_categories=('run',))
    select_package_decorators(args, decorators)
    return decorators


def _get_jobs(args, decorators):
    jobs = OrderedDict()
    for decorator in decorators:
        if not decorator.selected:
            continue

        pkg = decorator.descriptor

        extension = get_task_extension(
            'colcon_ros_buildfarm.task.build', pkg.type)
        if not extension:
            logger.warning(
                "No task extension to 'build' a '{pkg.type}' package"
                .format_map(locals()))
            continue

        recursive_dependencies = OrderedDict()
        for dep_name in decorator.recursive_dependencies:
            recursive_dependencies[dep_name] = dep_name

        task_context = TaskContext(
            pkg=pkg, args=args,
            dependencies=recursive_dependencies)

        job = Job(
            identifier=pkg.name,
            dependencies=set(recursive_dependencies.keys()),
            task=extension, task_context=task_context)

        jobs[job.identifier] = job

    return jobs


def _create_path(path):
    path = Path(os.path.abspath(path))
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    ignore_marker = path / IGNORE_MARKER
    if not os.path.lexists(str(ignore_marker)):
        with ignore_marker.open('w'):
            pass


class RosBuildfarmVerb(VerbExtensionPoint):
    """Build packages using the ROS buildfarm."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--ros-distro',
            default='rolling')

        parser.add_argument(
            '--build-name',
            default='default')
        parser.add_argument(
            '--config-url',
            default=DEFAULT_CONFIG_URL)

        parser.add_argument(
            '--build-base',
            default='buildfarm',
            help='The base path for all build directories '
                 '(default: buildfarm)')

        parser.add_argument(
            '--ros-buildfarm-branch',
            default='master',
            help='The branch of the ros-infrastructure/ros_buildfarm '
                 'repository to use for script generation and within each '
                 'build container')

        add_executor_arguments(parser)
        add_event_handler_arguments(parser)

        extensions = get_package_discovery_extensions()
        add_package_discovery_arguments(parser, extensions=extensions)
        add_package_selection_arguments(parser)

        add_task_arguments(parser, 'colcon_ros_buildfarm.task.build')
        add_package_repository_arguments(parser)

    def main(self, *, context):  # noqa: D102
        configure_ros_buildfarm_logger()

        _create_path(context.args.build_base)
        check_and_mark_build_tool(context.args.build_base)

        config_path = Path(context.args.build_base) / '_buildfarm_config'
        get_config(
            config_path, context.args.ros_distro, context.args.build_name,
            args=context.args, upstream_config_url=context.args.config_url)
        index_path = config_path / 'index.yaml'
        context.args.config_url = index_path.resolve().as_uri()

        decorators = _get_packages(context.args)

        jobs = _get_jobs(context.args, decorators)

        return execute_jobs(context, jobs)
