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
import json

from subprocess import call
from collections import deque
from threading import RLock
from os import devnull, symlink, unlink

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
    default_error_sound = "/home/pi/draht/sounds/horn.wav"
    default_finish_sound = "/home/pi/draht/sounds/horn.wav"

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

        self.observers = []

        GPIO.add_event_detect(self.wire_chan, GPIO.RISING, callback=self, bouncetime=500)

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

        self.notify()

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

    def register(self, observer):
        self.observers.append(observer)

    def notify(self):
        for observer in self.observers:
            observer.notify(self)

# ------------------------------------------------------------------------------
class WireGame:

    def __init__(self, players, reset):
        self.players = players
        self.round = None

        GPIO.add_event_detect(reset, GPIO.FALLING, callback=self, bouncetime=1000)

    def __call__(self, channel):
        logging.debug("reset event detected")
        self.round.reset()

    def run(self):
        logging.info("Everything armed and ready - waiting for action")
        while True:
            self.round = WireGameRound(self.players)
            if self.round.run():
                filename = "/home/pi/draht/web/%s.json" % self.round.round_id()
                linkname = "/home/pi/draht/web/latest.json"
                with open(filename, "w") as f:
                    f.write(self.round.json())
                unlink(linkname)
                symlink(filename, linkname)
                logging.debug("result JSON written to %s" % filename)

# ------------------------------------------------------------------------------
class WireGameRound:
    round = 0;
    sleep_time = 0.005

    def __init__(self, players):
        self.start = time.time()
        self.players = players
        WireGameRound.round += 1
        self.status = []
        self.rst = False

        for player in self.players:
            player.reset()
            self.status.append(False)

        logging.info("Round #%d created" % self.round)

    def run(self):
        finished = False

        while not finished:
            if self.rst:
                logging.info("Round #%d reset" % self.round)
                self.rst = False
                return False

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

        return True

    def json(self):
        result = {"start" : time.strftime("%d.%m.%Y %H:%M:%S", time.gmtime(self.start)), "round" : self.round, "results" : []}
        for player in self.players:
            result["results"].append({"id" : player.id, "time" : "%f" % (player.stop_time - player.start_time), "contacts" : player.contacts})

        return json.dumps(result)

    def round_id(self):
        return "%s--%03d" % (time.strftime("%Y%m%d%H%M%S", time.gmtime(self.start)), self.round)

    def reset(self):
        logging.debug("reset called")
        self.rst = True

# ------------------------------------------------------------------------------

class PlayerLedObserver:

    def __init__(self, red, yellow, green):
        self.red = red
        self.yellow = yellow
        self.green = green

    def notify(self, player):
        out_r = GPIO.HIGH
        out_y = GPIO.HIGH
        out_g = GPIO.HIGH

        if player.state == State.READY or player.state == State.INIT:
            out_g = GPIO.LOW
        elif player.state == State.PLAYING:
            out_y = GPIO.LOW
        elif player.state == State.FINISHED or player.state == State.WAIT:
            out_r = GPIO.LOW

        GPIO.output(self.red, out_r)
        GPIO.output(self.yellow, out_y)
        GPIO.output(self.green, out_g)

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

RESET     = 24
P1_GREEN  = 12
P1_YELLOW =  8
P1_RED    = 10
P2_GREEN  = 22
P2_YELLOW = 16
P2_RED    = 18

# Now we set the pins to be inputs and activate the
# pull-down resistor for each pin.

for channel in [P1_STRT, P1_WIRE, P1_STOP, P2_STRT, P2_WIRE, P2_STOP, RESET]:
    logging.debug("set input pin %d" % channel)
    GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Now we set the pins to be outputs and init them to high

for channel in [P1_GREEN, P1_YELLOW, P1_RED, P2_GREEN, P2_YELLOW, P2_RED]:
    logging.debug("set output pin %d" % channel)
    GPIO.setup(channel, GPIO.OUT, initial=GPIO.HIGH)

# Create the player objects

p1 = WirePlayer("Player 1", P1_STRT, P1_WIRE, P1_STOP)
p2 = WirePlayer("Player 2", P2_STRT, P2_WIRE, P2_STOP)

# Create observer for status LEDs

o1 = PlayerLedObserver(P1_RED, P1_YELLOW, P1_GREEN)
p1.register(o1)

o2 = PlayerLedObserver(P2_RED, P2_YELLOW, P2_GREEN)
p2.register(o2)

# customize settings

# p2.error_sound = "/home/pi/draht/sounds/buzz.wav"

# create the game object

game = WireGame([p1, p2], RESET)

# run :)

game.run()

# clean up everything GPIO related

GPIO.cleanup()

