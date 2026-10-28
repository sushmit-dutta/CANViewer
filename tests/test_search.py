import pytest

from canviewer.data import SignalInfo
from canviewer.search import SearchIndex, squash, words

CATALOG = [
    SignalInfo("Battery_Voltage", "BMS_Pack", 0x1A4, "V", "Pack terminal voltage", ("BMS",)),
    SignalInfo("Battery_Current", "BMS_Pack", 0x1A4, "A", "", ("BMS",)),
    SignalInfo("InverterTemp", "INV_Status", 0x2B0, "C", "Heatsink temperature", ("INV",)),
    SignalInfo("Fault_Code", "TCU_Faults", 0x300, "", "", ("TCU",)),
    SignalInfo("State", "TCU_State", 0x301, "", "", ("TCU",)),
]


@pytest.fixture
def index():
    return SearchIndex(CATALOG)


def names(result):
    return [s.name for s in result.signals]


def test_normalisation():
    assert squash("Battery_Voltage") == "batteryvoltage"
    assert words("InverterTemp_C") == ["inverter", "temp", "c"]


def test_separator_and_case_insensitive(index):
    assert "Battery_Voltage" in names(index.search("batteryvoltage"))
    assert "Battery_Voltage" in names(index.search("BATTERY VOLTAGE"))


def test_all_terms_must_match_in_any_order(index):
    assert names(index.search("volt batt")) == ["Battery_Voltage"]


def test_matches_message_node_unit_comment_and_id(index):
    assert names(index.search("INV_Status")) == ["InverterTemp"]
    assert "InverterTemp" in names(index.search("heatsink"))
    assert names(index.search("terminal")) == ["Battery_Voltage"]
    assert set(names(index.search("0x1a4"))) == {"Battery_Voltage", "Battery_Current"}
    assert names(index.search("0x2")) == ["InverterTemp"]  # id prefix, not substring
    assert set(names(index.search("bms amp"))) == set()  # unit is "A", not "amp"
    assert set(names(index.search("bms a"))) >= {"Battery_Current"}


def test_wildcards(index):
    assert set(names(index.search("batt*age"))) == {"Battery_Voltage"}
    assert names(index.search("fault_cod?")) == ["Fault_Code"]


def test_ranking_prefers_name_matches(index):
    result = names(index.search("state"))
    assert result[0] == "State"  # exact name before TCU_State signals


def test_message_names_are_reported(index):
    assert index.search("bms").messages == ["BMS_Pack"]


def test_fuzzy_fallback(index):
    result = index.search("btryvlt")
    assert result.fuzzy and names(result) == ["Battery_Voltage"]


def test_no_match_and_empty_query(index):
    assert index.search("zzzzzz").signals == []
    assert index.search("   ").signals == []


def test_limit_keeps_total(index):
    result = index.search("b", limit=1)
    assert len(result.signals) == 1 and result.total > 1
