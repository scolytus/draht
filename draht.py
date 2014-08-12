#!/usr/bin/python3

# draht.py is the software part of a wire loop game. It is itended to be run on
# a Raspberry Pi.
#
# Project site: https://github.com/scolytus/draht
#
# Copyright (C) 2014 Michael Gissing
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import RPi.GPIO as GPIO
import time
import logging

from subprocess import call
from collections import deque
from threading import RLock
from os import devnull

# ==============================================================================
# Class declarations
# ==============================================================================

class State:
    INIT = 1
    READY = 2
    PLAYING = 3
    FINISHED = 4
    WAIT = 5

    @staticmethod
    def to_string(state):
        if State.INIT == state:
            return "INIT"
        elif State.READY == state:
            return "READY"
        elif State.PLAYING == state:
            return "PLAYING"
        elif State.FINISHED == state:
            return "FINISHED"
        elif State.WAIT == state:
            return "WAIT"
        else:
            return "UNKNOWN"

class WirePlayer:
    default_error_sound = "/home/pi/horn.wav"
    default_finish_sound = "/home/pi/horn.wav"

    def __init__(self, id, start_chan, wire_chan, stop_chan):
        self.id = id
        self.start_chan = start_chan
        self.wire_chan = wire_chan
        self.stop_chan = stop_chan

        self.state = State.INIT
        self.contacts = 0
        self.time_start = 0
        self.time_finish = 0

        self.lock_wire_events = RLock()
        self.wire_events = 0

        self.error_sound = self.default_error_sound
        self.finish_sound = self.default_finish_sound

        GPIO.add_event_detect(self.wire_chan, GPIO.RISING, callback=self, bouncetime=200)

    # --------------------------------------------------------------------------
    # Count events
    def __call__(self, channel):
        if channel == self.wire_chan:
            with self.lock_wire_events:
                self.wire_events += 1

    # --------------------------------------------------------------------------
    def step(self):
        if State.INIT == self.state:
            # INIT state: wait till we have the hook on the start segment
            if GPIO.input(self.start_chan):
                self.state = State.READY

        elif State.READY == self.state:
            # READY state: in this state the hook is on the start segment
            if not GPIO.input(self.start_chan):
                # hook was lifted, start playing
                with self.lock_wire_events:
                    self.wire_events = 0
                self.contacts = 0
                self.start_time = time.time()
                self.state = State.PLAYING
                logging.debug("%s started playing" % self.id)

        elif State.PLAYING == self.state:
            # PLAYING state: Player is playing and we rely on event callbacks
            self.handle_events()

            if GPIO.input(self.start_chan):
                # hook on start position - reset game
                self.state = State.READY
            elif GPIO.input(self.stop_chan):
                # hook on stop position - game finished
                self.state = State.FINISHED
                self.stop_time = time.time()
                self.play_sound(self.finish_sound)
                logging.debug("%s finished playing in %f seconds with %d contacts" % (self.id, self.stop_time - self.start_time, self.contacts))

        elif State.FINISHED == self.state:
            # FINISHED state: wait till we have the hook on the start segment
            if GPIO.input(self.start_chan):
                self.state = State.READY

        elif State.WAIT == self.state:
            # WAIT state: do nothing :)
            pass

        else:
            raise Exception("Unknown State - dafuq?")

    # --------------------------------------------------------------------------
    def handle_events(self):
        play_sound = False

        with self.lock_wire_events:
            if self.wire_events > 0:
                self.contacts += self.wire_events
                logging.debug("Found %d new events - now we have %d contacts" % (self.wire_events, self.contacts))
                play_sound = True
                self.wire_events = 0

        if play_sound:
            self.play_sound(self.error_sound, 1)

    def play_sound(self, file, duration=0):
        with open(devnull, "w") as f:
            call("aplay -d %d %s &" % (duration, file), shell=True, stdout=f, stderr=f)

    def reset(self):
        self.state = State.INIT

    def wait(self):
        self.state = State.WAIT

    def result(self):
        return "%s in %f seconds with %d contacts" % (self.id, self.stop_time - self.start_time, self.contacts)

# ------------------------------------------------------------------------------
class WireGame:

    def __init__(self, players):
        self.players = players

    def run(self):
        logging.info("Everything armed and ready - waiting for action")
        while True:
            round = WireGameRound(self.players)
            round.run()
         
# ------------------------------------------------------------------------------
class WireGameRound:
    round = 0;
    sleep_time = 0.005

    def __init__(self, players):
        self.start = time.time()
        self.players = players
        WireGameRound.round += 1
        self.status = []

        for player in self.players:
            player.reset()
            self.status.append(False)

        logging.info("Round #%d created" % self.round)

    def run(self):
        finished = False
        while not finished:
            for idx, player in enumerate(self.players):
                if not self.status[idx]:
                    player.step()

                if player.state == State.FINISHED:
                    self.status[idx] = True
                    player.wait()

            finished = True
            for stat in self.status:
                finished = finished and stat

            time.sleep(self.sleep_time)

        logging.info("Round #%d ended" % self.round)
        for player in self.players:
            logging.info("    %s" % player.result())

# ==============================================================================
# Start of script
# ==============================================================================

# Setup logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s] %(message)s', datefmt='%Y%m%d %H:%M:%S')
logging.info("draht.py started - have fun :)")

# We use the BOARD numbering mode. This means the pin numbers are assigned
# as they are on the RasPi Pin header, no matter how they are wired to the SoC.
# This means this script will run on Rev 1 and 2 boards.

logging.debug("Set numbering mode")
GPIO.setmode(GPIO.BOARD)

# Assign the channel numbers to the internal descriptive names
P1_STRT = 11
P1_WIRE = 13
P1_STOP = 15
P2_STRT = 19
P2_WIRE = 21
P2_STOP = 23

# Now we set the pins to be inputs and activate the
# pull-down resistor for each pin.

for channel in [P1_STRT, P1_WIRE, P1_STOP, P2_STRT, P2_WIRE, P2_STOP]:
    logging.debug("set input pin %d" % channel)
    GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Create the player objects

p1 = WirePlayer("Spieler 1", P1_STRT, P1_WIRE, P1_STOP)
p2 = WirePlayer("Spieler 2", P2_STRT, P2_WIRE, P2_STOP)

# customize settings

p2.error_sound = "/home/pi/buzz.wav"

# create the game object

game = WireGame([p1, p2])

# run :)

game.run()

# clean up everything GPIO related

GPIO.cleanup()

