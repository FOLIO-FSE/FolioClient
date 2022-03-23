from unittest.mock import Mock
from folioclient import FolioClient
import pytest


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
