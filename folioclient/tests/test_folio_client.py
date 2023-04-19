import pytest
from folioclient import FolioClient
from httpx import HTTPError


def test_first():
    with pytest.raises(ValueError):
        FolioClient("", "", "", "")


""" def test_backwards():
    folio = FolioClient(
        "", "", "", ""
    )
    yaml = folio.get_latest_from_github(
        "folio-org", "mod-notes", "src/main/resources/swagger.api/schemas/note.yaml"
    )
    assert yaml["note"]["properties"] """


def test_get_notes_yaml_schema():
    yaml = FolioClient.get_latest_from_github(
        "folio-org", "mod-notes", "src/main/resources/swagger.api/schemas/note.yaml"
    )
    assert yaml["note"]["properties"]


def test_get_json_schema():
    json = FolioClient.get_latest_from_github(
        "folio-org", "mod-user-import", "ramls/schemas/userdataimport.json"
    )
    assert json["properties"]


def test_get_latest_from_github_returns_none_when_failing():
    with pytest.raises(HTTPError):
        FolioClient.get_latest_from_github("branchedelac", "tati", "myfile.json")


def test_get_latest_from_github_returns_file_1():
    schema = FolioClient.get_latest_from_github(
        "folio-org",
        "mod-source-record-manager",
        "/mod-source-record-manager-server/src/main/resources/rules/marc_holdings_rules.json",
    )
    assert schema is not None
    assert schema.get("001", None) is not None


def test_get_latest_from_github_returns_file_orgs_has_no_releases():
    with pytest.raises(HTTPError):
        FolioClient.get_latest_from_github(
            "folio-org",
            "acq-models",
            "/mod-orgs/schemas/organization.json",
        )
