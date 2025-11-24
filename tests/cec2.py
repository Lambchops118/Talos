import subprocess
import time
import sys

# Test code to turn on/off TV and switch inputs between different HDMI. Implement this in main program to "wake-up" the butler or shut down when needed.
# I wrote this with GPT-5.1.

# Command used to talk to libCEC via cec-client.
# -s  : single-command mode
# -d 1: log level 1 (errors only)

CEC_CLIENT_CMD = "cec-client -s -d 1"


def send_cec(cmd: str) -> int:
    """
    Send a single CEC command string via cec-client.

    Example commands:
      "on 0"     -> power on TV (logical address 0)
      "standby 0"-> put TV in standby
      "as"       -> set this device as active source
    """
    full_cmd = f'echo "{cmd}" | {CEC_CLIENT_CMD}'
    print(f"[DEBUG] Running: {full_cmd}")
    result = subprocess.run(full_cmd, shell=True)
    return result.returncode


def tv_power_on():
    """
    Power on the TV (logical address 0 is usually the TV).
    """
    print("Turning TV ON...")
    send_cec("on 0")


def tv_power_off():
    """
    Put the TV into standby.
    """
    print("Putting TV into standby...")
    send_cec("standby 0")


def switch_to_pi_input(): #Pi is responsible for MQTT broker and CEC program.
    """
    Switch the TV to the HDMI input that the Pi is on.

    The clean, high-level way:
      - 'as' tells the TV: 'I am the active source now.'
        Most TVs will switch to the HDMI port where this device is connected.

    Since your Pi reports physical address 1.0.0.0 (HDMI 1),
    this effectively switches the TV to HDMI 1.
    """
    print("Switching TV to the Pi's HDMI input...")
    # High-level 'active source' command:
    send_cec("as")

    # If for some reason 'as' doesn't behave the way you want,
    # you can try sending a routing/active-source frame explicitly
    # using what we learned from cec-client -d 8:
    #
    #   logical address of Pi: 1
    #   physical address of Pi: 1.0.0.0 (10:00)
    #
    # Uncomment the next line to experiment:
    # send_cec("tx 1F:82:10:00")

def switch_to_server_pc_input(): #Server PC is responsible for Monkey Butler core.
    print("Switching TV to the Pi's HDMI input...")
    send_cec("2.0.0.0")


def menu():
    while True:
        print("\n=== HDMI-CEC TV Control ===")
        print("1) Turn TV ON")
        print("2) Turn TV OFF (Standby)")
        print("3) Switch TV to Pi HDMI input")
        print("5) Switch TV to Server PC HDMI input")
        print("5) Quit")
        choice = input("Select an option (1-4): ").strip()

        if choice == "1":
            tv_power_on()
        elif choice == "2":
            tv_power_off()
        elif choice == "3":
            switch_to_pi_input()
        elif choice == "4":
            switch_to_server_pc_input()
        elif choice == "5":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nExiting on Ctrl+C")
        sys.exit(0)
