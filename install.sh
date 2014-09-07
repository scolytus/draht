#!/bin/bash
#
# Copyright (C) 2014 Michael Gissing
#
# Download and install draht.py from https://github.com/scolytus/draht on a
# Raspberry Pi
#

err() {
  echo "[ERROR] " $@
  exit -1
}

inf() {
  echo "[INFO ] " $@
}

DEST="/home/pi/draht"
ZIP="/tmp/draht.zip"

inf "check install directory"
[[ -d "${DEST}" ]] || mkdir "${DEST}" || err "can't create ${DEST}"

inf "check needed applications"
which gatling || err "gatling not installed - run 'apt-get install gatling'"
which aplay   || err "aplay not installed - run 'apt-get install alsaplayer'"

inf "download .zip from github.com"
wget https://github.com/scolytus/draht/archive/master.zip -O "${ZIP}" || err "can't download draht.zip"

inf "install stuff"
pushd $(mktemp -d)
unzip "${ZIP}"
mv draht-master/* "${DEST}"
popd

inf "add autostart to rc.local"
sudo sed -i $'${/^[ \t]*exit[ \t]\+0/[ -f /home/pi/draht/system/rc.local.sh ] && /home/pi/draht/system/rc.local.sh\n}' /etc/rc.local

inf "DONE :)"

