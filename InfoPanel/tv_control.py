import subprocess
import time
from typing import List, Optional

ADB_PATH = "adb"
TV_IP = "192.168.1.158"  # <-- change this to your Fire TV's IP
TV_PORT = 5555           # default ADB TCP port

# Keycodes
KEY_POWER_TOGGLE = "26"
KEY_SLEEP        = "223"
KEY_WAKE         = "224"  # may behave same as 26 on some Fire TVs

#HDMI Input Keycodes
KEY_HDMI1 = "243"
KEY_HDMI2 = "244"
KEY_HDMI3 = "245"

class FireTvController:
    def __init__(self, adb_path: str = ADB_PATH,
                 ip:   str = TV_IP,
                 port: int = TV_PORT) -> None:
        self.adb_path = adb_path
        self.target   = f"{ip}:{port}"

    def _run_adb(self, args: List[str],
                 check:          bool = False,
                 capture_output: bool = True,
                 text:           bool = True) -> subprocess.CompletedProcess:
        """
        Run adb command with -s <target> automatically.
        """
        cmd = [self.adb_path, "-s", self.target] + args
        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=text
        )

    def _run_adb_raw(self, args: List[str],
                     check:          bool = False,
                     capture_output: bool = True,
                     text:           bool = True) -> subprocess.CompletedProcess:
        """
        Run adb command without specifying a device (for connect/disconnect).
        """
        cmd = [self.adb_path] + args
        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=text
        )
    
    # Connection Management
    def connect(self) -> bool:
        """
        Connect to the Fire TV via TCP/IP.
        Returns True on success.
        """
        result = self._run_adb_raw(["connect", self.target])
        print(result.stdout.strip() or result.stderr.strip())
        return "connected to" in result.stdout.lower() or "already connected" in result.stdout.lower()

    def disconnect(self) -> None:
        """
        Disconnect this Fire TV.
        """
        result = self._run_adb_raw(["disconnect", self.target])
        print(result.stdout.strip() or result.stderr.strip())

    def is_connected(self) -> bool:
        """
        Check if this target shows up in `adb devices`.
        """
        result = self._run_adb_raw(["devices"])
        devices = result.stdout.strip().splitlines()[1:]  # skip header
        for line in devices:
            if self.target in line and "device" in line:
                return True
        return False
    
    # Generic Commands
    def send_key(self, keycode: str) -> None:
        """
        Send a keyevent by numeric code (e.g. "26", "223").
        """
        self._run_adb(["shell", "input", "keyevent", keycode])

    def send_key_name(self, name: str) -> None:
        """
        Send a keyevent by Android key name (e.g. "KEYCODE_HOME").
        """
        self._run_adb(["shell", "input", "keyevent", name])

    def shell(self, command: str) -> str:
        """
        Run an arbitrary shell command on the Fire TV and return stdout.
        """
        result = self._run_adb(["shell", command])
        return result.stdout
    
    #Power Controls
    def power_toggle(self) -> None:
        """
        Toggle power: wakes from sleep or puts to sleep.
        """
        self.send_key(KEY_POWER_TOGGLE)

    def wake(self) -> None:
        """
        Attempt to explicitly wake the TV.
        On many Fire TVs, KEY_POWER_TOGGLE will also wake.
        """
        self.send_key(KEY_WAKE)

    def sleep(self) -> None:
        """
        Put the TV into sleep/standby mode.
        """
        self.send_key(KEY_SLEEP)

    def wake_and_wait(self, delay: float = 5.0) -> None:
        """
        Wake the TV and wait a bit for UI to be responsive.
        """
        self.power_toggle()
        time.sleep(delay)

    #Navigation
    def home(self) -> None:
        self.send_key_name("KEYCODE_HOME")

    def back(self) -> None:
        self.send_key_name("KEYCODE_BACK")

    def menu(self) -> None:
        self.send_key_name("KEYCODE_MENU")

    def dpad_up(self) -> None:
        self.send_key_name("KEYCODE_DPAD_UP")

    def dpad_down(self) -> None:
        self.send_key_name("KEYCODE_DPAD_DOWN")

    def dpad_left(self) -> None:
        self.send_key_name("KEYCODE_DPAD_LEFT")

    def dpad_right(self) -> None:
        self.send_key_name("KEYCODE_DPAD_RIGHT")

    def select(self) -> None:
        self.send_key_name("KEYCODE_DPAD_CENTER")

    #Volume
    def volume_up(self) -> None:
        self.send_key_name("KEYCODE_VOLUME_UP")

    def volume_down(self) -> None:
        self.send_key_name("KEYCODE_VOLUME_DOWN")

    def mute(self) -> None:
        self.send_key_name("KEYCODE_VOLUME_MUTE")

    #HDMI Inputs
    def show_input_selector(self) -> None:
        """
        Show the input selection overlay.
        """
        self.send_key_name("KEYCODE_TV_INPUT")

    def hdmi1(self) -> None:
        self.send_key(KEY_HDMI1)

    def hdmi2(self) -> None:
        self.send_key(KEY_HDMI2)

    def hdmi3(self) -> None:
        self.send_key(KEY_HDMI3)

    #Launch Apps
    def launch_app(self, package_name: str) -> None:
        """
        Launch an app by package name using the monkey command.
        Example: com.netflix.ninja, com.amazon.avod.thirdpartyclient, etc.
        """
        self._run_adb([
            "shell", "monkey",
            "-p", package_name,
            "-c", "android.intent.category.LAUNCHER",
            "1"
        ])

    def list_running_activities(self) -> str:
        """
        Return a string describing the top activity / tasks.
        """
        return self.shell("dumpsys activity activities | grep -i 'top-activity'")