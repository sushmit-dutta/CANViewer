"""Shared fixtures: a tiny synthetic DBC and MF4 log (no real vehicle data)."""

from pathlib import Path

import cantools
import can
import pytest

DBC_TEXT = """VERSION ""

NS_ :

BS_:

BU_: BMS TCU

BO_ 256 Pack: 8 BMS
 SG_ Volt : 0|16@1+ (0.1,0) [0|6000] "V" Vector__XXX
 SG_ State : 16|8@1+ (1,0) [0|1] "" Vector__XXX

BO_ 512 Therm: 8 TCU
 SG_ Temp : 0|8@1- (1,0) [-50|150] "C" Vector__XXX

CM_ SG_ 256 Volt "pack voltage";
VAL_ 256 State 1 "Run" 0 "Idle" ;
"""

T0 = 1_790_000_000.0  # absolute Unix seconds, like real site logs
PACK_GAP = range(2, 30)  # Pack is silent for samples 2..29 (2.8 s)
N_STEPS = 50


@pytest.fixture(scope="session")
def dbc_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("dbc") / "t.dbc"
    path.write_text(DBC_TEXT)
    return path


def _messages(dbc_path):
    db = cantools.database.load_file(str(dbc_path))
    pack, therm = db.get_message_by_name("Pack"), db.get_message_by_name("Therm")
    for i in range(N_STEPS):
        t = T0 + i * 0.1
        if i not in PACK_GAP:
            yield can.Message(timestamp=t, arbitration_id=0x100, is_extended_id=False,
                              data=pack.encode({"Volt": 400 + i * 0.5, "State": i % 2}))
        if i % 10 == 0:
            yield can.Message(timestamp=t, arbitration_id=0x200, is_extended_id=False,
                              data=therm.encode({"Temp": 20 + i}))


@pytest.fixture(scope="session")
def mf4_path(tmp_path_factory, dbc_path) -> Path:
    path = tmp_path_factory.mktemp("log") / "log.mf4"
    with can.Logger(str(path)) as writer:
        writer._start_time = 0  # keep absolute timestamps, as the converter does
        for msg in _messages(dbc_path):
            writer(msg)
    return path


@pytest.fixture(scope="session")
def asc_path(tmp_path_factory, dbc_path) -> Path:
    path = tmp_path_factory.mktemp("asc") / "log.asc"
    with open(path, "w") as fh:
        writer = can.ASCWriter(fh)
        for msg in _messages(dbc_path):
            writer.on_message_received(msg)
        writer.stop()
    return path


@pytest.fixture(scope="session")
def log_data(mf4_path, dbc_path, tmp_path_factory):
    from canviewer.data import load_log

    return load_log(str(mf4_path), str(dbc_path), tz="UTC",
                    cache_dir=tmp_path_factory.mktemp("cache"))
