import subprocess
import time
from typing import List, Optional


# ==========================
# CONFIGURATION
# ==========================

# Path to adb. If adb is in your PATH, leave this as "adb".
# Otherwise, put the full path, e.g. r"C:\Android\platform-tools\adb.exe"
ADB_PATH = "adb"

# Fire TV IP (no port)
TV_IP = "192.168.1.123"  # <-- change this to your Fire TV's IP
TV_PORT = 5555           # default ADB TCP port

# Keycodes (these are typical; adjust if needed)
KEY_POWER_TOGGLE = "26"
KEY_SLEEP        = "223"
KEY_WAKE         = "224"  # may behave same as 26 on some Fire TVs

# HDMI input keycodes - these can vary slightly by Fire OS version.
# Test 243/244/245 on your TV and map them correctly.
KEY_HDMI1 = "243"
KEY_HDMI2 = "244"
KEY_HDMI3 = "245"


class FireTvController:
    """
    High-level wrapper around adb to control a Fire TV / Toshiba Fire TV.

    Make sure:
      - ADB debugging is enabled on the TV
      - You've done `adb connect <ip>:5555` at least once and accepted the prompt
    """

    def __init__(self, adb_path: str = ADB_PATH,
                 ip: str = TV_IP,
                 port: int = TV_PORT) -> None:
        self.adb_path = adb_path
        self.target = f"{ip}:{port}"

    # --------------------------
    # Internal helpers
    # --------------------------

    def _run_adb(self, args: List[str],
                 check: bool = False,
                 capture_output: bool = True,
                 text: bool = True) -> subprocess.CompletedProcess:
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
                     check: bool = False,
                     capture_output: bool = True,
                     text: bool = True) -> subprocess.CompletedProcess:
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

    # --------------------------
    # Connection management
    # --------------------------

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

    # --------------------------
    # Generic commands
    # --------------------------

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

    # --------------------------
    # Power controls
    # --------------------------

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

    # --------------------------
    # Navigation
    # --------------------------

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

    # --------------------------
    # Volume
    # --------------------------

    def volume_up(self) -> None:
        self.send_key_name("KEYCODE_VOLUME_UP")

    def volume_down(self) -> None:
        self.send_key_name("KEYCODE_VOLUME_DOWN")

    def mute(self) -> None:
        self.send_key_name("KEYCODE_VOLUME_MUTE")

    # --------------------------
    # HDMI / Inputs
    # --------------------------

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

    # --------------------------
    # Apps and activities
    # --------------------------

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

    # --------------------------
    # Screenshots
    # --------------------------

    def screenshot(self, remote_path: str = "/sdcard/firetvscreen.png",
                   local_path: Optional[str] = None) -> Optional[str]:
        """
        Take a screenshot on the Fire TV and optionally pull it to the PC.

        Returns local_path if pulled, otherwise the remote_path.
        """
        # Capture on device
        self._run_adb(["shell", "screencap", "-p", remote_path])

        if local_path is not None:
            # Pull to local machine
            result = self._run_adb(["pull", remote_path, local_path])
            print(result.stdout.strip() or result.stderr.strip())
            return local_path

        return remote_path


# ==========================
# Example usage
# ==========================

def main():
    tv = FireTvController()

    print(f"Connecting to {tv.target}...")
    if not tv.connect():
        print("Could not connect. Make sure ADB debugging is enabled on the TV and IP is correct.")
        return

    if not tv.is_connected():
        print("Device not listed in adb devices, aborting.")
        return

    print("Connected!")

    # Simple demo sequence:
    print("Waking TV and going to HDMI 2...")
    tv.wake_and_wait(delay=5)
    tv.hdmi2()

    print("Launching Netflix (if installed)...")
    tv.launch_app("com.netflix.ninja")

    time.sleep(5)
    print("Taking screenshot to firetv.png...")
    tv.screenshot(local_path="firetv.png")

    print("Putting TV to sleep in 5 seconds...")
    time.sleep(5)
    tv.sleep()

    print("Disconnecting...")
    tv.disconnect()


if __name__ == "__main__":
    main()