#!/bin/bash

if [ "$#" -lt 1 ]; then
    echo "Usage: ./hockeygamebot.sh <VENV|PYTHONEXEC> <SCRIPT-PARAMS:optional>"
    echo "VENV|PYTHONEXEC is the path to the virtual environment to active or the Python binary to use."
    echo "SCRIPT-PARAMS are the optional parameters being passed into the game bot script."
    exit 1
fi

if [[ "$@" == *"--console"* ]]; then
    echo "[WARN] The --console flag was detected. Please launch the script directly to log to the console."
    echo "Usage: python -m hockeygamebot <SCRIPT-PARAMS>"
    exit 1
fi


SCRIPTPATH=$(dirname "$0")
LOGFILE="${SCRIPTPATH}/hockeygamebot.log"
VENV=$1

# This sends all output to a file (regardless of output command)
exec &> $LOGFILE

echo "[INFO] Starting new instance of the Hockey Game Bot!"

# Change Directory into this script directory
cd $SCRIPTPATH
echo "[INFO] Moving to script directory - $(pwd)"

# Activate the Virtual Environment (Unless Python Executable)
if [[ $VENV == *"python"* ]]; then
    PYTHONEXEC=$VENV
else
    source $VENV/bin/activate
    PYTHONEXEC=$(command -v python)
fi

if [[ ! -x "$PYTHONEXEC" ]]; then
    echo "[ERROR] The Python executable '$PYTHONEXEC' is not valid - please validate and try again."
    exit 1
fi

echo "[INFO] Using the following Python executable - $PYTHONEXEC"

# Perform a `git pull` to make sure our code is up to date
echo "[INFO] Doing a 'git pull' to make sure we have the most up to date code."
git pull

# Shift the input arguments by 2 (to get to the Python script arguments)
shift 1

# "$@" passes all arguments from the bash script into the python script
echo "[INFO] Executing the following game bot script."
echo "[EXEC] $PYTHONEXEC -m hockeygamebot $*"
nohup $PYTHONEXEC -m hockeygamebot "$@" 2>&1 | tee &
