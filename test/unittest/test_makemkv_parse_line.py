"""Tests for parsing makemkvcon --robot output lines"""
import pytest

import arm.ui  # noqa: F401 - import order: arm.ui before the ripper (arm.models)
from arm.ripper import makemkv

READ_ERROR = "Error 'Scsi error - MEDIUM ERROR' occurred while reading"


@pytest.mark.parametrize("line", [
    "MSG:5010,0",  # truncated header
    'MSG:abc,0,0,"x","x"',
    "DRV:0,1",
    "TINFO:1,2",
    "SINFO:1",
    "CINFO:1",
    "PRGV:1",
    "TCOUNT:x",
])
def test_malformed_records_are_parser_errors(line):
    with pytest.raises(makemkv.MakeMkvParserError):
        makemkv.parse_line(line)


@pytest.mark.parametrize("line", [
    f'MSG:2003,0,1,"{READ_ERROR}","%1"',  # format without its parameter
    f'MSG:2003,0,0,"{READ_ERROR}"',
    'MSG:2019,0,0,"Error writing"',
    'MSG:5080,0,0,"Backup Mode Failed"',
    "MSG:5080,0,0",  # the code alone is still a backup failure
])
def test_error_records_without_parameters_are_still_errors(line):
    msg_type, message = makemkv.parse_line(line)
    assert msg_type == makemkv.OutputType.MSG
    assert isinstance(message, makemkv.MakeMKVErrorMessage)
    assert message.error


def test_error_record_with_parameters_keeps_its_error_text():
    line = (f'MSG:2003,0,3,"{READ_ERROR} \'/dev/sr0\' at offset \'0\'",'
            '"Error \'%1\' occurred while reading \'%2\' at offset \'%3\'",'
            '"Scsi error - MEDIUM ERROR","/dev/sr0","0"')
    _, message = makemkv.parse_line(line)
    assert message.error == "Scsi error - MEDIUM ERROR"
    assert message.sprintf == ["/dev/sr0", "0"]


@pytest.mark.parametrize("line", [
    'MSG:5004,0,0,"x titles saved","%1 titles saved, %2 failed"',
    'MSG:5004,0,0,"x"',
    'MSG:5004,0,2,"0 titles saved, 2 failed","%1 titles saved, %2 failed","0","2"',
    'MSG:5004,0,2,"-1 titles saved, 2 failed","%1 titles saved, %2 failed","-1","2"',
])
def test_unreadable_or_zero_rip_summary_fails_the_rip(line):
    with pytest.raises(makemkv.MakeMkvRuntimeError):
        makemkv.parse_line(line)


class FakeMakemkvcon:
    """Stands in for subprocess.Popen(makemkvcon ...) with fixed stdout lines"""

    def __init__(self, lines, returncode=0):
        self.stdout = [line + "\n" for line in lines]
        self.returncode = returncode
        self.pid = 1234

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_malformed_lines_are_skipped_and_the_rip_completes(monkeypatch):
    output = ["MSG:5010,0", "TINFO:1,2", 'MSG:5005,0,1,"2 titles saved","%1 titles saved","2"']
    monkeypatch.setattr(makemkv.shutil, "which", lambda name: "/usr/bin/makemkvcon")
    monkeypatch.setattr(makemkv.subprocess, "Popen", lambda cmd, **kwargs: FakeMakemkvcon(output))
    messages = list(makemkv.run(["mkv", "dev:/dev/sr0", "all", "/raw"], makemkv.OutputType.MSG))
    assert [message.code for message in messages] == [5005]


def test_title_error_without_text_still_fails_the_rip(monkeypatch):
    monkeypatch.setattr(makemkv.shutil, "which", lambda name: "/usr/bin/makemkvcon")
    monkeypatch.setattr(makemkv.subprocess, "Popen", lambda cmd, **kwargs: FakeMakemkvcon(["MSG:5003,0,0"]))
    with pytest.raises(makemkv.MakeMkvRuntimeError):
        list(makemkv.run(["mkv", "dev:/dev/sr0", "all", "/raw"], makemkv.OutputType.MSG))
