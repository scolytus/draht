#!/bin/bash

LOG_DIR=/var/log/draht
WWW_LOG="${LOG_DIR}/access.log"
GAME_LOG="${LOG_DIR}/game.log"

[[ -d "${LOG_DIR}" ]] || mkdir "${LOG_DIR}"

# start gatling web server
pushd /home/pi/draht/web &> /dev/null
echo "========== $(date) ==========" >> "${WWW_LOG}"
gatling -U -D -F -u nobody >> "${WWW_LOG}" 2>&1 &
popd &> /dev/null

# start game
pushd /home/pi/draht &> /dev/null
./draht.py >> "${GAME_LOG}" 2>&1 &
popd &> /dev/null

# done :)

