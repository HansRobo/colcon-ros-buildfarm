# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

from colcon_core.plugin_system import satisfies_version
from colcon_ros_buildfarm.config_augmentation \
    import ConfigAugmentationExtensionPoint
from colcon_ros_buildfarm.config_augmentation import logger
import yaml


BUILD_TYPES = {
    'ci_builds',
    'doc_builds',
    'release_builds',
    'source_builds',
}


class DropJenkinsConfigAugmentation(ConfigAugmentationExtensionPoint):
    """Modify local config cache to remove jenkins-specific data."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ConfigAugmentationExtensionPoint.EXTENSION_POINT_VERSION,
            '^1.0')

    def augment_config(self, config_path, args):  # noqa: D102
        index_path = config_path / 'index.yaml'
        with index_path.open('r') as f:
            index_data = yaml.safe_load(f)

        logger.debug(
            'Looking for Jenkins-specific data in {index_path}'.format_map(
                locals()))

        index_data['jenkins_url'] = None
        index_data.pop('doc_builds', None)
        index_data.pop('git_ssh_credential_id', None)
        index_data.pop('status_page_repositories', None)

        for build_types in index_data.get('distributions', {}).values():
            build_types.pop('ci_builds', None)
            build_types.pop('doc_builds', None)
            build_types.pop('source_builds', None)
            for build_type in BUILD_TYPES.intersection(build_types.keys()):
                for build_file_path in build_types[build_type].values():
                    self._augment_build_file(config_path / build_file_path)

        with index_path.open('w') as f:
            yaml.dump(index_data, f)

    def _augment_build_file(self, build_file_path):
        with build_file_path.open('r') as f:
            build_file_data = yaml.safe_load(f)

        build_file_data.pop('jenkins_binary_job_priority', None)
        build_file_data.pop('jenkins_binary_job_timeout', None)
        build_file_data.pop('jenkins_source_job_priority', None)
        build_file_data.pop('jenkins_source_job_timeout', None)
        build_file_data.pop('sync', None)

        with build_file_path.open('w') as f:
            yaml.dump(build_file_data, f)
