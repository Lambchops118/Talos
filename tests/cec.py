import subprocess
import time

class TVControllerCEC:
    def __init__(self, cec_client_cmd="cec-client -s -d 1"):
        self.cec_client_cmd = cec_client_cmd

    def _send(self, cmd: str):
        full_cmd = f'echo "{cmd}" | {self.cec_client_cmd}'
        subprocess.run(full_cmd, shell=True, check=False)

    def power_on(self):
        # TV is usually logical address 0
        self._send("on 0")

    def standby(self):
        # Put TV into standby
        self._send("standby 0")

    def set_active_source(self):
        # Declare this device the active source (TV usually switches to this HDMI)
        self._send("as")

    def switch_to_hdmi2(self):
        # May need adjusting depending on your TV wiring
        # 4F:82:20:00 = broadcast routing change/active source to physical 2.0.0.0
        self._send("tx 4F:82:20:00")

if __name__ == "__main__":
    tv = TVControllerCEC()
    tv.power_on()
    time.sleep(5)   # give TV a moment to wake up
    tv.switch_to_hdmi2()
