# pylint: disable=wrong-import-position
"""Main run page for armui"""
import os
import sys
import signal
import socket

# set the PATH to /arm/arm, so we can handle imports properly
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import arm.config.config as cfg  # noqa E402
import arm.ui.routes  # noqa E402
import arm.ui.settings.DriveUtils  # noqa E402
import arm.ui.utils  # noqa E402

from arm.ui import app  # noqa E402

shutdown_requested = False


def startup():
    """ARM UI Startup check on database config"""
    db_update = arm.ui.utils.arm_db_check()
    if db_update["db_current"]:
        app.logger.info("Updating Optical Drives")
        arm.ui.settings.DriveUtils.drives_update(startup=True)


def handle_shutdown(signum, frame):
    """ARM handle SIGTERM/SIGINT for graceful shutdown"""
    global shutdown_requested
    shutdown_requested = True
    app.logger.info("Received shutdown signal (%s). Shutting down ARM-UI.", signum)
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGTERM, handle_shutdown)      # systemd shutdown command
signal.signal(signal.SIGINT, handle_shutdown)       # keyboard interrupt


def is_docker():
    """
    Test to check if running inside a docker/container
    returns: Boolean
    """
    path = '/proc/self/cgroup'

    if os.path.exists('/.dockerenv'):
        return True

    if os.path.isfile(path):
        with open(path) as f:
            return any('docker' in line for line in f)

    return False


ALL_INTERFACES = '0.0.0.0'


def local_addresses():
    """IPv4 and IPv6 addresses of this machine's network interfaces"""
    from netifaces import interfaces, ifaddresses, AF_INET, AF_INET6
    addresses = set()
    for interface in interfaces():
        links = ifaddresses(interface)
        for link in links.get(AF_INET, []) + links.get(AF_INET6, []):
            addresses.add(link['addr'].split('%')[0])  # drop an IPv6 zone such as %eth0
    return addresses


def is_local_address(host):
    """True if ``host`` (an address or a host name) resolves to an address of this machine"""
    try:
        resolved = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError):
        return False
    return not resolved.isdisjoint(local_addresses())


def get_host():
    """
    Address for the web server to listen on

    With WEBSERVER_IP 'x.x.x.x' (autodetect), and always inside docker, listen on all interfaces.
    Picking one interface address at startup served on 127.0.0.1 when the network wasn't up yet,
    e.g. after a reboot (#1390). Notification links still use the detected address (utils.check_ip).
    An address that isn't this machine's can't be listened on, so log that and listen on all
    interfaces instead of failing to start (#1576).
    """
    host = str(cfg.arm_config['WEBSERVER_IP'])
    if host == 'x.x.x.x' or is_docker():
        return ALL_INTERFACES
    if host in (ALL_INTERFACES, '::') or is_local_address(host):
        return host
    app.logger.error(
        "WEBSERVER_IP '%s' is not an address of this machine, so the web server can't listen on it. "
        "Listening on all interfaces (%s) instead. Set WEBSERVER_IP to one of this machine's addresses, "
        "or to x.x.x.x.", host, ALL_INTERFACES)
    return ALL_INTERFACES


# Start ARM using waitress, default number of threads is "4", set ARM count to "40"
# Higher thread count to accommodate slow blocking processes when the UI is polling the ripper during ripping
if __name__ == '__main__':
    host = get_host()
    port = cfg.arm_config['WEBSERVER_PORT']
    app.logger.info("Starting ARM-UI on interface address - %s:%s", host, port)

    # Run ARM Startup
    startup()

    from waitress import serve

    try:
        serve(app, host=host, port=port, threads=40)
    except KeyboardInterrupt:
        app.logger.info("Keyboard interrupt received, shutting down ARM-UI.")
    finally:
        app.logger.info("ARM-UI shutdown complete.")
