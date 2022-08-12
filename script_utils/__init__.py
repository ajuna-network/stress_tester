
import logging
import re
import os
import subprocess

from substrateinterface import Keypair


def get_submodule_commit_sha(submodule_path):
    version_str = subprocess.check_output(
        ['git', 'submodule', 'status', submodule_path]).decode('ascii')

    version_str = version_str.replace('+', '')

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


def get_integritee_cli(docker_exec, worker_container):
    container_path = f'{worker_container}:/service/integritee-cli'
    cmd = [docker_exec, 'cp', container_path, '.']

    logging.info(
        f'Extracting integritee-cli from "{container_path}" container...')

    process = subprocess.run(cmd)
    process.check_returncode()

    logging.info(f'Extraction succesfull!')

    return os.path.abspath('integritee-cli')


def get_mrenclave(cli_exec):
    logging.info(f'Parsing MRENCLAVE...')
    cmd = get_base_cli_cmd(cli_exec) + ['list-workers']

    process = subprocess.run(cmd, stdout=subprocess.PIPE)
    output = process.stdout.decode('ascii')

    matches = re.findall(r'MRENCLAVE: (\w+)', output)

    if matches:
        mrenclave = matches[0]
        logging.info(F'Parsed MRENCLAVE: "{mrenclave}"')
        return mrenclave
    else:
        logging.error(
            'Failed in locating MRENCLAVE, is the worker running and reachable?')
        exit(1)


def get_base_cli_cmd(cli_exec, node_port=9944, worker_port=2011, websocket_ip='127.0.0.1'):
    return [cli_exec, '-p', str(node_port), '-P', str(worker_port), '-u', f'ws://{websocket_ip}', '-U', f'wss://{websocket_ip}']


def get_trusted_cli_subcommand(call_signer, mrenclave, subcmd):
    return ['trusted', '--xt-signer', call_signer, '--direct', '--mrenclave', mrenclave, subcmd]


def sort_accounts_by_public_key(account_uri_list):
    return sorted(account_uri_list, key=lambda x: Keypair.create_from_uri(x).public_key)


class BoardParseException(Exception):
    pass


class BoardParser:
    EMPTY = 'Empty'
    STONE = 'Stone'
    BOMB = 'Bomb'
    BLOCK = 'Block'

    def __init__(self, board_string):
        try:
            cells_list = board_string.split('[[')[1].split(']]')[0].replace(
                ']', '').replace('[', '').split(', ')
            self._board_matrix = [
                cells_list[i * 10:(i * 10) + 10] for i in range(10)]
        except Exception:
            raise BoardParseException

    def compute_bomb_orders(self, update_matrix=False):
        bomb_orders = []

        for i in range(10):
            for j in range(10):
                if self._board_matrix[i][j] == BoardParser.EMPTY:
                    bomb_orders.append((str(i), str(j)))
                    if update_matrix:
                        self._board_matrix[i][j] = BoardParser.BOMB

                    if len(bomb_orders) == 3:
                        return bomb_orders

        return bomb_orders

    def compute_stone_orders(self, player_1, player_2, update_matrix=False):
        def is_valid_row(cells_matrix, row_index, start_point, direction):

            row_can_fit_stones = (cells_matrix[row_index][start_point] == BoardParser.EMPTY and
                    cells_matrix[row_index][start_point + direction] == BoardParser.EMPTY and
                    cells_matrix[row_index][start_point + (direction * 2)] == BoardParser.EMPTY and
                    cells_matrix[row_index][start_point + (direction * 3)] == BoardParser.EMPTY)
            
            if row_can_fit_stones:
                i = start_point + (direction * 3)
                while i > 0 and i < len(cells_matrix[row_index]):
                    if cells_matrix[row_index][i] == BoardParser.BLOCK:
                        return True
                    i += direction
            
            return False

        def is_valid_col(cells_matrix, col_index, start_point, direction):

            col_can_fit_stones = (cells_matrix[start_point][col_index] == BoardParser.EMPTY and
                    cells_matrix[start_point + direction][col_index] == BoardParser.EMPTY and
                    cells_matrix[start_point + (direction * 2)][col_index] == BoardParser.EMPTY and
                    cells_matrix[start_point + (direction * 3)][col_index] == BoardParser.EMPTY)

            if col_can_fit_stones:
                i = start_point + (direction * 3)
                while i > 0 and i < len(cells_matrix):
                    if cells_matrix[i][col_index] == BoardParser.BLOCK:
                        return True
                    i += direction
            
            return False

        def drop_stones_in_row(cells_matrix, row_index, start_point, direction):
            true_start_point = start_point
            for i in range(10):
                moved_start_point = start_point + (i * direction)
                if cells_matrix[row_index][start_point + (i * direction)] != BoardParser.EMPTY:
                    true_start_point = moved_start_point

            i = 4
            r = 0
            while i > 0:
                if cells_matrix[row_index][true_start_point + r] == BoardParser.EMPTY:
                    cells_matrix[row_index][true_start_point +
                                            r] = BoardParser.STONE
                    i -= 1
                r += direction

        def drop_stones_in_col(cells_matrix, col_index, start_point, direction):
            true_start_point = start_point
            for i in range(10):
                moved_start_point = start_point + (i * direction)
                if cells_matrix[start_point + (i * direction)][col_index] != BoardParser.EMPTY:
                    true_start_point = moved_start_point

            i = 4
            r = 0
            while i > 0:
                if cells_matrix[true_start_point + r][col_index] == BoardParser.EMPTY:
                    cells_matrix[true_start_point +
                                 r][col_index] = BoardParser.STONE
                    i -= 1
                r += direction

        stone_orders_player_1 = []
        stone_orders_player_2 = []

        # Check west side
        for i in range(10):
            if is_valid_row(self._board_matrix, i, 0, 1):
                if len(stone_orders_player_1) == 0:
                    stone_orders_player_1 = [('west', str(i))] * 4
                elif len(stone_orders_player_2) == 0:
                    stone_orders_player_2 = [('west', str(i))] * 4
                else:
                    return {player_1: stone_orders_player_1, player_2: stone_orders_player_2}

                if update_matrix:
                    drop_stones_in_row(self._board_matrix, i, 9, -1)

        # Check east side
        for i in range(10):
            if is_valid_row(self._board_matrix, i, 9, -1):
                if len(stone_orders_player_1) == 0:
                    stone_orders_player_1 = [('east', str(i))] * 4
                elif len(stone_orders_player_2) == 0:
                    stone_orders_player_2 = [('east', str(i))] * 4
                else:
                    return {player_1: stone_orders_player_1, player_2: stone_orders_player_2}

                if update_matrix:
                    drop_stones_in_row(self._board_matrix, i, 0, 1)

        # Check north side
        for i in range(10):
            if is_valid_col(self._board_matrix, i, 0, 1):
                if len(stone_orders_player_1) == 0:
                    stone_orders_player_1 = [('north', str(i))] * 4
                elif len(stone_orders_player_2) == 0:
                    stone_orders_player_2 = [('north', str(i))] * 4
                else:
                    return {player_1: stone_orders_player_1, player_2: stone_orders_player_2}

                if update_matrix:
                    drop_stones_in_col(self.__board_matrix, i, 9, -1)

        # Check south side
        for i in range(10):
            if is_valid_col(self._board_matrix, i, 9, -1):
                if len(stone_orders_player_1) == 0:
                    stone_orders_player_1 = [('south', str(i))] * 4
                elif len(stone_orders_player_2) == 0:
                    stone_orders_player_2 = [('south', str(i))] * 4
                else:
                    return {player_1: stone_orders_player_1, player_2: stone_orders_player_2}

                if update_matrix:
                    drop_stones_in_col(self._board_matrix, i, 0, 1)

        return {player_1: stone_orders_player_1, player_2: stone_orders_player_2}
