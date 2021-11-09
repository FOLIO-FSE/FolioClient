# content of test_sample.py
from uuid import uuid5
from folio_uuid import FolioUUID, folio_uuid

from folio_uuid.folio_namespaces import FOLIONamespaces

made_up_okapi_url = "https://okapi.folio.ebsco.com"


def test_deterministic_uuids_namespace_generation():
    u1 = uuid5(FolioUUID.base_namespace, "items")
    assert str(u1) == str(FOLIONamespaces.items.value)


def test_deterministic_uuid_generation_basic():
    deterministic_uuid = FolioUUID(made_up_okapi_url, FOLIONamespaces.items, "test")
    assert "b720a97c-ccc5-5e4f-9091-6809b6174b9c" == str(deterministic_uuid)


def test_deterministic_uuid_generation_sierra_weak_record_key():
    deterministic_uuid = FolioUUID(
        made_up_okapi_url,
        FOLIONamespaces.items,
        "i3696836",
    )
    assert "2a3e016e-188c-59bf-a3d8-24b52b2e5775" == str(deterministic_uuid)


def test_deterministic_uuid_generation_sierra_strong_record_key():
    deterministic_uuid = FolioUUID(
        made_up_okapi_url,
        FOLIONamespaces.items,
        "i36968365",
    )
    assert "2a3e016e-188c-59bf-a3d8-24b52b2e5775" == str(deterministic_uuid)


def test_deterministic_uuid_generation_sierra_strong_record_key_dot():
    deterministic_uuid = FolioUUID(
        made_up_okapi_url,
        FOLIONamespaces.items,
        ".i36968365",
    )
    assert "2a3e016e-188c-59bf-a3d8-24b52b2e5775" == str(deterministic_uuid)


def test_checkdigit_creation():
    """Translated to python from https://github.com/SydneyUniLibrary/sierra-record-check-digit/blob/master/index-test.js"""
    known_check_digits = [
        [100114, "0"],
        [2539964, "0"],
        [100610, "1"],
        [1655776, "1"],
        [583623, "2"],
        [1629736, "2"],
        [572288, "3"],
        [4093863, "3"],
        [284683, "4"],
        [3898776, "4"],
        [395792, "5"],
        [3040121, "5"],
        [542671, "6"],
        [2626834, "6"],
        [459573, "7"],
        [2699873, "7"],
        [581326, "8"],
        [2054794, "8"],
        [539148, "9"],
        [1203395, "9"],
        [585345, "x"],
        [1562237, "x"],
    ]

    for combo in known_check_digits:
        assert FolioUUID.calculate_sierra_check_digit(combo[0]) == combo[1]


def test_obvious_record_numbers_with_check_digits():
    ids = [
        ["b33846327", "b3384632"],
        ["b47116523@mdill", "b4711652"],
        ["o100007x", "o100007"],
        ["b1125421x", "b1125421"],
        [".b1125421x", "b1125421"],
        ["#b33846327", "#b33846327"],
        ["b", "b"],
        [".b", ".b"],
        ["9999999", "9999999"],
        ["https://id.kb.se/fnrgl", "https://id.kb.se/fnrgl"],
        ["111", "111"],
        ["111111111111", "111111111111"],
        ["b12345", "b12345"],
        ["b4711652@", "b4711652@"],
        ["b4711652@toolong", "b4711652@toolong"],
        [".b12345", ".b12345"],
        [".b4711652@", ".b4711652@"],
        [".b4711652@toolong", ".b4711652@toolong"],
    ]

    for id_combo in ids:
        assert FolioUUID.clean_iii_identifiers(id_combo[0]) == id_combo[1]
