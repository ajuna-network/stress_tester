#!/usr/bin/python3

import argparse
import logging
from multiprocessing import Pool
import os
import shutil
import subprocess
import sys
import time

from substrateinterface import SubstrateInterface, Keypair

import script_utils as scu


def generate_player_account(cli_cmd, account_name, balance, stdout_type):
    logging.debug(f'"{account_name}" Setting funds...')
    cmd = cli_cmd + [account_name, str(balance)]
    proc = subprocess.run(cmd, stdout=stdout_type, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        logging.error(
            f'Error setting funds to {account_name}: {proc.stdout.decode("ascii")}')
        return False
    else:
        logging.info(f'"{account_name}" Transfer succesfull!')
        return True


def generate_player_accounts(cli_exec, mrenclave, player_count, ws_addr='127.0.0.1', ws_port=9944, balance=1_000_000_000, verbose=False):
    def transfer_funds_to_created_accounts(rpc_node, alice_keypair, account_name, balance):
        logging.info(f'Tranfering {balance} funds to {account_name}')
        try:
            account_keypair = Keypair.create_from_uri(account_name)
            alice_keypair = Keypair.create_from_uri('//Alice')
            call = rpc_node.compose_call(
                call_module='Balances',
                call_function='transfer',
                call_params={
                    'dest': account_keypair.ss58_address,
                    'value': balance
                }
            )
            extrinsic = rpc_node.create_signed_extrinsic(
                call=call, keypair=alice_keypair)
            receipt = rpc_node.submit_extrinsic(
                extrinsic, wait_for_inclusion=True)
            logging.info(
                f'Funds transferred to {account_name}!')
            logging.debug(
                f'Transfer receipt identifier {receipt.get_extrinsic_identifier()}')
            logging.debug(f'{receipt.extrinsic}')
            return True
        except Exception as ex:
            logging.error(f'Failed to transfer funds: {ex}')

    base_name = '//Account_'

    logging.info(f'Creating {player_count} player accounts...')

    if verbose:
        stdout_type = subprocess.PIPE
    else:
        stdout_type = subprocess.DEVNULL

    base_cli_cmd = scu.get_base_cli_cmd(cli_exec)

    account_names = [(base_cli_cmd + scu.get_trusted_cli_subcommand(f'{base_name}{i}', mrenclave, 'set-balance'), f'{base_name}{i}', balance, stdout_type)
                     for i in range(0, player_count)]

    proc_count = min(len(os.sched_getaffinity(0)), player_count)

    with Pool(proc_count) as pool:
        pool.starmap(generate_player_account, account_names)

    try:
        logging.info(f'Connecting to Ajuna node...')
        node = SubstrateInterface(url=f'ws://{ws_addr}:{ws_port}')
    except Exception as ex:
        logging.error(f'Failed to connect to node: {ex}')
        exit(1)

    alice_keypair = Keypair.create_from_uri('//Alice')

    for account_tuple in account_names:
        transfer_funds_to_created_accounts(
            node, alice_keypair, account_tuple[1], balance)

    return [acc[1] for acc in account_names]


def drop_bomb(cli_cmd, player, col, row, log_file):
    cmd = cli_cmd + [player, col, row]
    logging.debug(f'Running command: "{" ".join(cmd)}"')
    p = subprocess.run(cmd, stdout=log_file,
                       stderr=subprocess.STDOUT, timeout=60.0)
    p.check_returncode()


def drop_stone(cli_cmd, player, direction, x, log_file):
    cmd = cli_cmd + [player, direction, x]
    logging.debug(f'Running command: "{" ".join(cmd)}"')
    p = subprocess.run(cmd, stdout=log_file,
                       stderr=subprocess.STDOUT, timeout=60.0)
    p.check_returncode()


def check_board(cli_cmd, player, log_file):
    cmd = cli_cmd + [player]
    logging.debug(f'Running command: "{" ".join(cmd)}"')
    p = subprocess.run(cmd, stdout=log_file,
                       stderr=subprocess.STDOUT, timeout=60.0)
    p.check_returncode()


def compute_playing_positions(cli_cmd, player_1, player_2):
    cmd = cli_cmd + [player_1]

    p = subprocess.run(cmd, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=60.0, text=True)
    p.check_returncode()

    cmd_output = p.stdout
    if 'could not fetch board' in cmd_output:
        logging.warning(
            f'Failed to fetch board for {player_1} - {player_2} game, trying once more in 30s...')

        time.sleep(30)

        p = subprocess.run(cmd, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=60.0, text=True)
        p.check_returncode()

        cmd_output = p.stdout
        if 'could not fetch board' in cmd_output:
            raise subprocess.CalledProcessError(
                cmd=' '.join(cmd), returncode=1, output=p.stdout)

    # Extract the board cells and convert them to a list
    parser = scu.BoardParser(cmd_output)

    bomb_orders = parser.compute_bomb_orders(update_matrix=True)
    stone_orders = parser.compute_stone_orders(
        player_1, player_2, update_matrix=True)

    return {'bomb_orders': bomb_orders, 'stone_orders': stone_orders}


def play_game(cli_exec, mrenclave, account_1, account_2):
    player_1, player_2 = scu.sort_accounts_by_public_key(
        [account_1, account_2])

    epoch = int(time.time())
    player_names = f'{account_1.replace("//", "")}-{account_2.replace("//", "")}'

    base_cli_cmd = scu.get_base_cli_cmd(cli_exec)

    with open(f'game-logs/{epoch}-{player_names}-game.log', 'w+') as game_log_file:

        logging.info(f'Starting game between {account_1} and {account_2}')
        logging.info(f'Player 1 is {player_1}, Player 2 is {player_2}')

        try:
            playing_positions = compute_playing_positions(
                base_cli_cmd + scu.get_trusted_cli_subcommand(player_1, mrenclave, 'get-board'), player_1, player_2)

            check_board(base_cli_cmd + scu.get_trusted_cli_subcommand(player_1,
                                                                      mrenclave, 'get-board'), player_1, game_log_file)
            # Place bombs for player one
            for order in playing_positions['bomb_orders']:
                drop_bomb(base_cli_cmd + scu.get_trusted_cli_subcommand(player_1, mrenclave, 'drop-bomb'),
                          player_1, order[1], order[0], game_log_file)
                check_board(base_cli_cmd + scu.get_trusted_cli_subcommand(player_1,
                                                                          mrenclave, 'get-board'), player_1, game_log_file)

            for order in playing_positions['bomb_orders']:
                drop_bomb(base_cli_cmd + scu.get_trusted_cli_subcommand(player_2, mrenclave, 'drop-bomb'),
                          player_2, order[1], order[0], game_log_file)
                check_board(base_cli_cmd + scu.get_trusted_cli_subcommand(player_2,
                                                                          mrenclave, 'get-board'), player_2, game_log_file)

            # Place stones alternatively for each player
            for i in range(4):
                for player in [player_1, player_2]:
                    order = playing_positions['stone_orders'][player][i]
                    drop_stone(base_cli_cmd + scu.get_trusted_cli_subcommand(player, mrenclave, 'drop-stone'),
                               player, order[0], order[1], game_log_file)
                    check_board(base_cli_cmd + scu.get_trusted_cli_subcommand(player,
                                                                              mrenclave, 'get-board'), player, game_log_file)

        except subprocess.CalledProcessError as cpe:
            logging.error(f'Game {account_1} <-> {account_2} failed to play turn: {cpe.output}')
            return False
        except subprocess.TimeoutExpired as tee:
            logging.error(f'Timeout expired for {player_names} game!')
            return False

    logging.info(
        f'Game {player_1} <-> {player_2} finished succesfully!')


def launch_games(cli_exec, mrenclave, player_list, num_procs=None):
    cli_extrinsic = ['queue-game']

    cli_cmd = scu.get_base_cli_cmd(cli_exec) + cli_extrinsic
    # Detect somehow if games get stuck
    for player in player_list:
        logging.info(f'"{player}" queueing for game')
        cmd = cli_cmd + [player]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            logging.error(
                f'Error queueing game for {player}: {proc.stdout.decode("ascii")}')
        else:
            logging.info(
                f'"{player}" queued succesfully: {proc.stdout.decode("ascii")}!')

    logging.info(f'Waiting 45s for boards to initialize...')
    time.sleep(45)
    logging.info(f'Starting games...')
    player_pairs_list = [(cli_exec, mrenclave, p[0], p[1])
                         for p in zip(player_list[::2], player_list[1::2])]

    try:
        os.mkdir('game-logs')
    except Exception:
        pass
    
    if num_procs is None:
        proc_count = min(len(os.sched_getaffinity(0)), len(player_pairs_list))
    else:
        proc_count = num_procs

    with Pool(proc_count) as pool:
        pool.starmap(play_game, player_pairs_list)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--games', required=True,
                        help='Amount of games to play', type=int)
    parser.add_argument('--processes', required=False, help='Maximum number of processes tu launch, detaults to "len(os.sched_getaffinity(0))"', type=int)
    parser.add_argument('--container', required=False, default='stress_tester-worker-1',
                        help='Name of the worker container from which to extract the "integritee-cli"', type=str)
    parser.add_argument('--verbose', required=False,
                        help='Show additional logging messages', action='store_true')

    args = parser.parse_args()

    scu.setup_logging(verbose=args.verbose)

    if (docker_path := shutil.which('docker')) is not None:
        logging.debug(f'Docker path: {docker_path}')

        cli_path = scu.get_integritee_cli(docker_path, args.container)
        mrenclave = scu.get_mrenclave(cli_path)
        account_number = args.games * 2
        account_list = generate_player_accounts(
            cli_path, mrenclave, account_number, verbose=args.verbose)

        logging.info(f'Launching {args.games} game/s...')
        launch_games(cli_path, mrenclave, account_list, args.processes)

    else:
        logging.error('Docker binary could not be located! Exiting...')
        sys.exit(1)
