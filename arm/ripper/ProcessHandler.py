"""
Function definition
  Wrapper for the python subprocess module
"""

import logging
import signal
import subprocess
from typing import Optional, List, Union


def _describe(error: subprocess.CalledProcessError) -> str:
    """How the command ended: its exit status, or the signal that killed it (e.g. SIGSEGV)."""
    if error.returncode < 0:
        try:
            return f"died with {signal.Signals(-error.returncode).name}"
        except ValueError:
            return f"died with signal {-error.returncode}"
    return f"exited with status {error.returncode}"


def arm_subprocess(cmd: Union[str, List[str]], shell=False, check=False, timeout=None,
                   expected_returncodes=(), failure_level=logging.ERROR) -> Optional[str]:
    """
    Spawn blocking subprocess

    :param cmd: Command to run
    :param shell: Run ``cmd`` in a shell
    :param check: Raise ``CalledProcessError`` if ``cmd`` returns non-zero exit code
    :param timeout: Seconds before ``cmd`` is killed; ``None`` waits indefinitely
    :param expected_returncodes: Non-zero exit codes that are a normal answer (logged at DEBUG)
    :param failure_level: Log level for other failures; a traceback is only attached at ERROR or above

    :return: Output (both stdout and stderr) of ``cmd``, or ``None`` if it returned a non-zero exit code
        or timed out

    :raise CalledProcessError:
    :raise TimeoutExpired: only when ``check`` is set
    """
    arm_process = None
    logging.debug(f"Running command: {cmd}")
    try:
        arm_process = subprocess.check_output(
            cmd,
            shell=shell,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        # check_output has already killed the command
        logging.log(failure_level, f"Command did not finish within {timeout}s and was stopped: {cmd}")
        if check:
            raise error
    except (subprocess.CalledProcessError, OSError) as error:
        decoded_output: Optional[str] = None
        if isinstance(error, subprocess.CalledProcessError):
            decoded_output = (error.output or "").strip()
            if error.returncode in expected_returncodes:
                logging.debug(f"Command {cmd} {_describe(error)}")
                if check:
                    raise error
                return None
            reason = _describe(error)
        else:
            reason = str(error)
        logging.log(
            failure_level,
            f"Error while running command: {cmd} ({reason})\n"
            + (
                f"Output was: {decoded_output}"
                if decoded_output
                else "The command produced no output."
            ),
            exc_info=error if failure_level >= logging.ERROR else None,
        )
        if check:
            raise error

    return arm_process
