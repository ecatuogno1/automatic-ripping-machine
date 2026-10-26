"""
Class definition
 Server - class for managing system utilisation
"""

import threading
import time

import psutil

import arm.config.config as cfg
from arm.ui import app
from flask import flash

GIB = 1073741824
# (sensor chip, labels to prefer in order); the chip's first reading is the fallback
TEMPERATURE_SENSORS = (
    ("coretemp", ("Package id 0",)),  # Intel
    ("k10temp", ("Tctl", "Tdie")),  # AMD
    ("zenpower", ("Tctl", "Tdie")),  # AMD (zenpower driver)
    ("cpu_thermal", ()),  # Raspberry Pi
    ("atk0110", ("CPU Temperature",)),  # AMD systems (Phenom)
    ("nct6797", ("CPUTIN", "SYSTIN")),  # AMD systems (Phenom)
)


def _busy_and_total(times):
    fields = times._asdict()
    # On Linux guest time is already counted in user/nice
    total = sum(fields.values()) - fields.get("guest", 0) - fields.get("guest_nice", 0)
    idle = fields.get("idle", 0) + fields.get("iowait", 0)
    return total - idle, total


class CpuSampler:
    """
    Busy CPU percent between samples taken at least ``min_window`` seconds apart, without sleeping.\n
    psutil.cpu_percent() without an interval returns 0.0 on its first call and, when two pages are built
    close together, measures a window of a few milliseconds. The baseline here lives at module level, so
    it survives the new ServerUtil every page builds.
    """

    def __init__(self, times=psutil.cpu_times, clock=time.monotonic, min_window=1.0):
        self._times, self._clock, self._min_window = times, clock, min_window
        self._lock = threading.Lock()
        self._value = None
        try:
            self._baseline = (self._clock(), _busy_and_total(self._times()))
        except (OSError, AttributeError):
            self._baseline = None

    def percent(self):
        """The last measured percent, refreshed when the window has passed; None until the first window"""
        with self._lock:
            try:
                now, sample = self._clock(), _busy_and_total(self._times())
            except (OSError, AttributeError):
                return self._value
            if self._baseline is None:
                self._baseline = (now, sample)
                return self._value
            started, (busy, total) = self._baseline
            if now - started >= self._min_window and sample[1] > total:
                share = (sample[0] - busy) / (sample[1] - total)
                self._value = round(min(max(share, 0.0), 1.0) * 100, 1)
                self._baseline = (now, sample)
            return self._value


CPU = CpuSampler()


def cpu_temperature(temps):
    """CPU temperature in °C from psutil.sensors_temperatures(); None when no known sensor reports one"""
    for chip, preferred in TEMPERATURE_SENSORS:
        readings = [r for r in temps.get(chip) or [] if r.current is not None and r.current > 0]
        if not readings:
            continue
        for label in preferred:
            for reading in readings:
                if reading.label == label:
                    return reading.current
        return readings[0].current
    return None


class ServerUtil():
    cpu_util = None
    cpu_temp = None
    memory_free = 0.0
    memory_used = 0.0
    memory_percent = 0.0
    # Hard drive space
    storage_raw_free = None
    storage_raw_percent = None
    storage_transcode_free = None
    storage_transcode_percent = None
    storage_completed_free = None
    storage_completed_percent = None

    def __init__(self):
        self.get_update()

    def get_update(self):
        self.get_cpu_util()
        self.get_cpu_temp()
        self.get_memory()
        self.storage_raw_free, self.storage_raw_percent = \
            self.get_disk_space(cfg.arm_config['RAW_PATH'])
        self.storage_transcode_free, self.storage_transcode_percent = \
            self.get_disk_space(cfg.arm_config['TRANSCODE_PATH'])
        self.storage_completed_free, self.storage_completed_percent = \
            self.get_disk_space(cfg.arm_config['COMPLETED_PATH'])

    def get_cpu_util(self):
        self.cpu_util = CPU.percent()
        app.logger.debug(f"Server CPU Util: {self.cpu_util}")

    def get_cpu_temp(self):
        try:
            temps = psutil.sensors_temperatures()
            app.logger.debug(f"cpu_temp: {temps}")
            self.cpu_temp = cpu_temperature(temps)
        except (OSError, AttributeError):  # psutil has no sensors_temperatures on macOS/Windows
            self.cpu_temp = None
        app.logger.debug(f"Server CPU Temp:  {self.cpu_temp}")

    def get_memory(self):
        try:
            memory = psutil.virtual_memory()
            # "Used" is what is not available, so used + free is the total and matches memory.percent
            self.memory_free = round(memory.available / GIB, 1)
            self.memory_used = round((memory.total - memory.available) / GIB, 1)
            self.memory_percent = memory.percent
        except EnvironmentError:
            self.memory_free = 0
            self.memory_used = 0
            self.memory_percent = 0
        app.logger.debug(f"Server Mem Free:  {self.memory_free}")
        app.logger.debug(f"Server Mem Used:  {self.memory_used}")
        app.logger.debug(f"Server Mem Percent:  {self.memory_percent}")

    def get_disk_space(self, filepath):
        # Hard drive space
        try:
            usage = psutil.disk_usage(filepath)
            disk_space = round(usage.free / GIB, 1)
            disk_percent = usage.percent
        except OSError:
            # None (not 0) so the page can tell an unreadable path from a full disk
            disk_space = None
            disk_percent = None
            app.logger.debug("ARM folders not found")
            flash("There was a problem accessing the ARM folder: "
                  f"'{filepath}'. Please make sure you have setup ARM", "danger")
        app.logger.debug(f"Server {filepath} Space:  {disk_space}")
        app.logger.debug(f"Server {filepath} Percent:  {disk_percent}")
        return disk_space, disk_percent
