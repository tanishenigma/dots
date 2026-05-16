#!/usr/bin/env python3
import fcntl

import gi

gi.require_version("Playerctl", "2.0")
import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional

import gi
from gi.repository import GLib, Playerctl
from gi.repository.Playerctl import Player

logger = logging.getLogger(__name__)

CLICK_WINDOW_SECONDS = 0.35
HIDDEN_WORKSPACE_NAME = "special:hidden"
CLICK_STATE_PATH = Path(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "waybar-mediaplayer-clicks.json"

def signal_handler(sig, frame):
    logger.info("Received signal to stop, exiting")
    sys.stdout.write("\n")
    sys.stdout.flush()
    # loop.quit()
    sys.exit(0)


def run_quietly(command):
    subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def read_json_command(command):
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def read_click_state(file_handle):
    file_handle.seek(0)
    raw_state = file_handle.read().strip()
    if not raw_state:
        return {}

    try:
        return json.loads(raw_state)
    except json.JSONDecodeError:
        return {}


def register_click(window_seconds: float) -> Optional[int]:
    CLICK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with CLICK_STATE_PATH.open("a+", encoding="utf-8") as state_file:
        fcntl.flock(state_file, fcntl.LOCK_EX)
        state = read_click_state(state_file)
        now = time.monotonic()
        last_click = float(state.get("last_click", 0.0))
        click_count = int(state.get("count", 0)) if now - last_click <= window_seconds else 0
        token = uuid.uuid4().hex

        state_file.seek(0)
        state_file.truncate()
        json.dump(
            {
                "count": click_count + 1,
                "last_click": now,
                "token": token,
            },
            state_file,
        )
        state_file.flush()
        os.fsync(state_file.fileno())
        fcntl.flock(state_file, fcntl.LOCK_UN)

    time.sleep(window_seconds)

    with CLICK_STATE_PATH.open("r+", encoding="utf-8") as state_file:
        fcntl.flock(state_file, fcntl.LOCK_EX)
        state = read_click_state(state_file)
        if state.get("token") != token:
            fcntl.flock(state_file, fcntl.LOCK_UN)
            return None

        click_count = int(state.get("count", 1))
        state_file.seek(0)
        state_file.truncate()
        state_file.flush()
        os.fsync(state_file.fileno())
        fcntl.flock(state_file, fcntl.LOCK_UN)
        return click_count


def find_player_client(player_name: str):
    clients = read_json_command(["hyprctl", "clients", "-j"])
    if not isinstance(clients, list):
        return None

    pattern = re.compile(rf"\b{re.escape(player_name)}\b", re.IGNORECASE)
    for client in clients:
        if not isinstance(client, dict):
            continue

        window_class = client.get("class")
        window_title = client.get("title")
        if isinstance(window_class, str) and pattern.search(window_class):
            return client
        if isinstance(window_title, str) and pattern.search(window_title):
            return client

    return None


def bring_player_to_current_workspace(player_name: str):
    player_client = find_player_client(player_name)
    player_address = player_client.get("address") if isinstance(player_client, dict) else None
    if not player_address:
        run_quietly(["omarchy-launch-or-focus", player_name])
        return

    active_workspace = read_json_command(["hyprctl", "activeworkspace", "-j"])
    workspace_target = None
    if isinstance(active_workspace, dict):
        workspace_target = active_workspace.get("name") or active_workspace.get("id")

    if workspace_target is not None:
        run_quietly(
            [
                "hyprctl",
                "dispatch",
                "movetoworkspacesilent",
                f"{workspace_target},address:{player_address}",
            ]
        )

    run_quietly(["hyprctl", "dispatch", "focuswindow", f"address:{player_address}"])


def toggle_player_hidden_workspace(player_name: str):
    player_client = find_player_client(player_name)
    player_address = player_client.get("address") if isinstance(player_client, dict) else None
    if not player_address:
        run_quietly(["omarchy-launch-or-focus", player_name])
        return

    workspace = player_client.get("workspace") if isinstance(player_client, dict) else None
    workspace_name = workspace.get("name") if isinstance(workspace, dict) else None
    if workspace_name == HIDDEN_WORKSPACE_NAME:
        bring_player_to_current_workspace(player_name)
        return

    run_quietly(
        [
            "hyprctl",
            "dispatch",
            "movetoworkspacesilent",
            f"{HIDDEN_WORKSPACE_NAME},address:{player_address}",
        ]
    )


def handle_click(player_name: str, click_window: float):
    click_count = register_click(click_window)
    if click_count is None:
        return

    playerctl_command = ["playerctl", "--player", player_name]
    if click_count == 1:
        run_quietly(playerctl_command + ["play-pause"])
    else:
        run_quietly(playerctl_command + ["next"])


def handle_right_click(player_name: str):
    toggle_player_hidden_workspace(player_name)


class PlayerManager:
    def __init__(self, selected_player=None, excluded_player=[]):
        self.manager = Playerctl.PlayerManager()
        self.loop = GLib.MainLoop()
        self.manager.connect(
            "name-appeared", lambda *args: self.on_player_appeared(*args))
        self.manager.connect(
            "player-vanished", lambda *args: self.on_player_vanished(*args))

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        self.selected_player = selected_player
        self.excluded_player = excluded_player.split(',') if excluded_player else []

        self.init_players()

    def init_players(self):
        for player in self.manager.props.player_names:
            if player.name in self.excluded_player:
                continue
            if self.selected_player is not None and self.selected_player != player.name:
                logger.debug(f"{player.name} is not the filtered player, skipping it")
                continue
            self.init_player(player)

    def run(self):
        logger.info("Starting main loop")
        self.loop.run()

    def init_player(self, player):
        logger.info(f"Initialize new player: {player.name}")
        player = Playerctl.Player.new_from_name(player)
        player.connect("playback-status",
                       self.on_playback_status_changed, None)
        player.connect("metadata", self.on_metadata_changed, None)
        self.manager.manage_player(player)
        self.on_metadata_changed(player, player.props.metadata)

    def get_players(self) -> List[Player]:
        return self.manager.props.players

    def write_output(self, text, player):
        logger.debug(f"Writing output: {text}")

        output = {"text": text,
                  "class": "custom-" + player.props.player_name,
                  "alt": player.props.player_name}

        sys.stdout.write(json.dumps(output) + "\n")
        sys.stdout.flush()

    def clear_output(self):
        sys.stdout.write("\n")
        sys.stdout.flush()

    def on_playback_status_changed(self, player, status, _=None):
        logger.debug(f"Playback status changed for player {player.props.player_name}: {status}")
        self.on_metadata_changed(player, player.props.metadata)

    def get_first_playing_player(self):
        players = self.get_players()
        logger.debug(f"Getting first playing player from {len(players)} players")
        if len(players) > 0:
            # if any are playing, show the first one that is playing
            # reverse order, so that the most recently added ones are preferred
            for player in players[::-1]:
                if player.props.status == "Playing":
                    return player
            # if none are playing, show the first one
            return players[0]
        else:
            logger.debug("No players found")
            return None

    def show_most_important_player(self):
        logger.debug("Showing most important player")
        # show the currently playing player
        # or else show the first paused player
        # or else show nothing
        current_player = self.get_first_playing_player()
        if current_player is not None:
            self.on_metadata_changed(current_player, current_player.props.metadata)
        else:    
            self.clear_output()

    def on_metadata_changed(self, player, metadata, _=None):
        logger.debug(f"Metadata changed for player {player.props.player_name}")
        player_name = player.props.player_name
        artist = player.get_artist()
        artist = artist.replace("&", "&amp;")
        title = player.get_title()
        title = title.replace("&", "&amp;")

        track_info = ""
        if player_name == "spotify" and "mpris:trackid" in metadata.keys() and ":ad:" in player.props.metadata["mpris:trackid"]:
            track_info = "Advertisement"
        elif artist is not None and title is not None:
            track_info = f"{artist} - {title}"
        else:
            track_info = title

        if track_info:
            if player.props.status == "Playing":
                track_info = "  " + track_info
            else:
                track_info = "  " + track_info
        # only print output if no other player is playing
        current_playing = self.get_first_playing_player()
        if current_playing is None or current_playing.props.player_name == player.props.player_name:
            self.write_output(track_info, player)
        else:
            logger.debug(f"Other player {current_playing.props.player_name} is playing, skipping")

    def on_player_appeared(self, _, player):
        logger.info(f"Player has appeared: {player.name}")
        if player.name in self.excluded_player:
            logger.debug(
                "New player appeared, but it's in exclude player list, skipping")
            return
        if player is not None and (self.selected_player is None or player.name == self.selected_player):
            self.init_player(player)
        else:
            logger.debug(
                "New player appeared, but it's not the selected player, skipping")

    def on_player_vanished(self, _, player):
        logger.info(f"Player {player.props.player_name} has vanished")
        self.show_most_important_player()

def parse_arguments():
    parser = argparse.ArgumentParser()

    # Increase verbosity with every occurrence of -v
    parser.add_argument("-v", "--verbose", action="count", default=0)

    parser.add_argument("command", nargs="?", choices=["listen", "click", "right-click"], default="listen")

    parser.add_argument(
        "-x",
        "--exclude",
        help="Comma-separated list of excluded player",
    )

    # Define for which player we"re listening
    parser.add_argument("--player")
    parser.add_argument("--click-window", type=float, default=CLICK_WINDOW_SECONDS)

    parser.add_argument("--enable-logging", action="store_true")

    return parser.parse_args()


def main():
    arguments = parse_arguments()

    # Initialize logging
    if arguments.enable_logging:
        logfile = os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "media-player.log")
        logging.basicConfig(filename=logfile, level=logging.DEBUG,
                            format="%(asctime)s %(name)s %(levelname)s:%(lineno)d %(message)s")

    # Logging is set by default to WARN and higher.
    # With every occurrence of -v it's lowered by one
    logger.setLevel(max((3 - arguments.verbose) * 10, 0))

    if arguments.command == "click":
        handle_click(arguments.player or "spotify", arguments.click_window)
        return
    if arguments.command == "right-click":
        handle_right_click(arguments.player or "spotify")
        return

    logger.info("Creating player manager")
    if arguments.player:
        logger.info(f"Filtering for player: {arguments.player}")
    if arguments.exclude:
        logger.info(f"Exclude player {arguments.exclude}")

    player = PlayerManager(arguments.player, arguments.exclude)
    player.run()


if __name__ == "__main__":
    main()
