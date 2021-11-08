# content of test_sample.py
from uuid import uuid5
from determid.determid import DetermId

from determid.folio_namespaces import FOLIONamespaces


def test_deterministic_uuids_namespace_generation():
    u1 = uuid5(DetermId.base_namespace, "items")
    assert str(u1) == str(FOLIONamespaces.items.value)


def test_deterministic_uuid_generation():
    u1 = DetermId("fs00001", FOLIONamespaces.items, "test")
    assert "8eec379a-c007-5911-a2a8-4ba460ecc2e3" == str(u1)
