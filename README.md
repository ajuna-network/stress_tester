# stress_tester

This repository is intended to streamline the execution of stress tests on the [node](https://github.com/ajuna-network/Ajuna) and [worker](https://github.com/ajuna-network/worker) repositories.

The repository contains two scripts `launch_infrastructure.py` and `launch_tests.py`, the first one is used to build and launch the container for the node and worker, the second script created a series of accounts and the uses them to play games on that infrastructure.

Both scripts have help commands to clarify their usage.

## Requirements

The project requires Python >= 3.8 and the installation of the requirements found in the `requirements.txt` file.

## Behaviour

When tests are run, for each individual game a specific log file will be created in the `game-logs` directory, in there you can check the specific details of each game.
