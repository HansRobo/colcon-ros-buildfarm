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


class DropUnusedConfigAugmentation(ConfigAugmentationExtensionPoint):
    """Modify local config cache to remove references to unused build files."""

    PRIORITY = 200

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
            'Looking for unused build file entries in {index_path}'.format_map(
                locals()))

        for build_types in index_data.get('distributions', {}).values():
            for build_type in BUILD_TYPES.intersection(build_types.keys()):
                build_file_names = list(build_types[build_type].keys())
                for build_file_name in build_file_names:
                    if not (
                        config_path / build_types[build_type][build_file_name]
                    ).is_file():
                        logger.debug(
                            'Dropping unused build file: {}'.format(
                                build_types[build_type][build_file_name]))
                        del build_types[build_type][build_file_name]

        with index_path.open('w') as f:
            yaml.dump(index_data, f)
