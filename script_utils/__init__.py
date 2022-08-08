
import logging
import subprocess


def get_submodule_commit_sha(submodule_path):
    version_str = subprocess.check_output(
        ['git', 'submodule', 'status', submodule_path]).decode('ascii')

    return version_str.strip().split(' ')[0][0:8]


def get_node_image_base_name():
    return 'ajuna.io/node-solo'


def get_worker_image_base_name():
    return 'ajuna.io/worker'


def setup_logging(verbose=False):
    log_format = ('[%(asctime)s][%(levelname)-5s] - %(message)s')

    if verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(
        level=log_level,
        format=log_format,
    )
