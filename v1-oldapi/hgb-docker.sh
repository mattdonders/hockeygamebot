#!/bin/bash

ostream() {
    if [ "$1" == "BLANK" ]; then
        echo "" | tee -a ${LOGFILE}
    else
        echo $(date +%Y-%m-%d) $(date +%T) "[ $1 ] $2" 2>&1 | tee -a ${LOGFILE}
    fi
}

if [ "$#" -lt 2 ]; then
    echo "Usage: ./hgb-docker.sh <team-name> </local/path/to/config> <extra-args>"
    exit 1
fi

TEAMNAME=$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr -d "[:space:]")
CONFIG=$2

# Shift the input arguments by 2 (to get to any extra script arguments)
shift 2

OTHERARGS=""
for var in "$@"; do
    OTHERARGS="-e ${OTHERARGS}${var} "
done

# Get Timezone from Local File (or use NY as Default)
if [ -f /etc/timezone ]; then
   TIMEZONE=$(cat /etc/timezone)
else
   TIMEZONE="America/New_York"
fi

# Check the memory on the server (useful for GCE instnances)
TOTALMEM=$(free -m | awk '/^Mem:/{print $2}')
TOTALSWAP=$(free -m | awk '/^Swap:/{print $2}')


if [ ! -f "$CONFIG" ]; then
    ostream ERROR "Specified config file does not exist - verify and try again."
    exit 1
fi

# Docker Pull (always have latest)
ostream INFO "Veriying we have the latest Docker image - will pull if not."
docker pull mattdonders/nhl-twitter-bot:latest
ostream BLANK

# Remove all Exited containers (to keep the instance clean)
ostream INFO "Cleaning up containers over a week old now & renaming to avoid conflicts."
docker rename hgb-"$TEAMNAME" hgb-"$TEAMNAME"-$(date +%s) > /dev/null 2>&1
docker rm $(docker ps -f status=exited | grep -E 'week[s]* ago' | awk '{print $1}') > /dev/null 2>&1

# Create Docker Container
if [ "$TOTALMEM" -lt "1024" ]; then
    ostream INFO "The total memory on this machine is less than 1GB - checking for swap."
    [ -z $TOTALSWAP ] && { ostream ERROR "No swap is available - cannot continue, exiting."; exit 1; }

    docker run --memory="500m" --memory-swap="-1" -d \
        --name hgb-"$TEAMNAME" -e TZ="$TIMEZONE" \
        -v "$CONFIG":/app/hockeygamebot/config/config.yaml \
        "$OTHERARGS" \
        mattdonders/nhl-twitter-bot:latest
else
    docker run -d --name hgb-"$TEAMNAME" -e TZ="$TIMEZONE" \
        -v "$CONFIG":/app/hockeygamebot/config/config.yaml \
        "$OTHERARGS" \
        mattdonders/nhl-twitter-bot:latest
fi

