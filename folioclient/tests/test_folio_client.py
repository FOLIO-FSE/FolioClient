from folioclient import FolioClient
import pytest


def test_first():
    with pytest.raises(ValueError):
        FolioClient("", "", "", "")
