#!/usr/bin/python3

import argparse
import logging
import os.path
import shutil
import subprocess
import sys

import script_utils


def build_image(docker_exec, dockerfile_path, image_base_name, submodule_path, verbose=False):
    node_hash = script_utils.get_submodule_commit_sha(submodule_path)
    image_name = f'{image_base_name}:{node_hash}'
    env = {'DOCKER_BUILDKIT': '1'}

    cmd = [docker_exec, 'build', '-f', dockerfile_path, '-t', image_name, '.']

    logging.info(
        f'Building image for submodule {submodule_path} at commit {node_hash}...')
    if verbose:
        stdout_type = sys.stdout
    else:
        stdout_type = subprocess.DEVNULL

    process = subprocess.run(cmd, stdout=stdout_type, text=True,
                             stderr=subprocess.STDOUT, env=env)

    if process.returncode != 0:
        error_log_file = f'{os.path.basename(submodule_path)}.log'
        logging.error(
            f'Error building image, check output of {error_log_file}')
        with open(error_log_file, 'w') as f:
            f.write(process.stdout)

        exit(1)
    else:
        logging.info(f'Image built succesfully: {image_name}')
        return image_name


def build_node_image(docker_exec, verbose=False):
    dockerfile = 'Dockerfile.node'
    submodule_path = os.path.abspath('node')
    base_name = 'ajuna.io/node-solo'

    return build_image(docker_exec, dockerfile, base_name, submodule_path, verbose)


def build_worker_image(docker_exec, verbose=False):
    dockerfile = 'Dockerfile.worker'
    submodule_path = os.path.abspath('worker')
    base_name = 'ajuna.io/worker'

    return build_image(docker_exec, dockerfile, base_name, submodule_path, verbose)


def start_infraestructure(docker_exec, compose_path, node_image, worker_image, verbose=False):
    logging.info(
        f'Starting up compose with {node_image} and {worker_image}...')

    env = {'NODE_IMAGE': node_image, 'WORKER_IMAGE': worker_image}
    cmd = [docker_exec, 'compose', '-f', compose_path, 'up']

    if verbose:
        stdout_type = sys.stdout
    else:
        stdout_type = subprocess.DEVNULL

    try:
        subprocess.run(
            cmd, stdout=stdout_type, stderr=subprocess.STDOUT, env=env)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', required=False,
                        help='Rebuild node and/or worker before launching tests', action='store_true')
    parser.add_argument('--verbose', required=False,
                        help='Show additional logging messages', action='store_true')

    args = parser.parse_args()

    script_utils.setup_logging(verbose=args.verbose)

    if (docker_path := shutil.which('docker')) is not None:
        logging.debug(f'Docker path: {docker_path}')
        if args.build:
            node_image = build_node_image(docker_path, args.verbose)
            worker_image = build_worker_image(docker_path, args.verbose)
        else:
            node_image_sha = script_utils.get_submodule_commit_sha(
                os.path.abspath('node'))
            node_image = f'{script_utils.get_node_image_base_name()}:{node_image_sha}'

            worker_image_sha = script_utils.get_submodule_commit_sha(
                os.path.abspath('worker'))
            worker_image = f'{script_utils.get_worker_image_base_name()}:{worker_image_sha}'
            logging.debug(
                f'Build flag set to "{args.build}", skipping build...')

        compose_path = os.path.abspath('docker-compose.yml')

        start_infraestructure(docker_path, compose_path,
                              node_image, worker_image, args.verbose)

    else:
        logging.error('Docker binary could not be located! Exiting...')
        sys.exit(1)
