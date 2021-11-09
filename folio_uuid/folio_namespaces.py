import uuid
import enum


class FOLIONamespaces(enum.Enum):
    """
    ENUM for UUID v5 Namespaces. Helping the FolioUUID to create
    unique deterministic uuids within a folio tenant
    """

    # Inventory
    # uuid.uuid5(FolioUUID.base_namespace, "holdings")
    holdings = uuid.UUID("81b6a778-b024-5050-9712-81d01c2ee33b")
    # uuid.uuid5(FolioUUID.base_namespace, "items")
    items = uuid.UUID("4ccaf819-a366-55f2-9a99-4e37f8d4031b")
    # uuid.uuid5(FolioUUID.base_namespace, "instances")
    instances = uuid.UUID("09d734f7-d5df-5fa1-9b5e-31d34f4bcfef")

    # SRS
    # uuid.uuid5(FolioUUID.base_namespace, "srs_records")
    srs_records = uuid.UUID("13e60b21-777c-5cb6-b7d8-2855b5d41852")
    # uuid.uuid5(FolioUUID.base_namespace, "raw_records")
    raw_records = uuid.UUID("cd2ba9c1-bb21-5148-8a39-3190fd78a047")
    # uuid.uuid5(FolioUUID.base_namespace, "parsed_records")
    parsed_records = uuid.UUID("9857b7bc-569c-53e4-bb1f-5449f8c4f62b")

    # Circulation
    # uuid.uuid5(FolioUUID.base_namespace, "loans")
    loans = uuid.UUID("08fb857e-4aeb-5eb8-a497-68495cc894f2")
    # uuid.uuid5(FolioUUID.base_namespace, "requests")
    requests = uuid.UUID("85934592-11a7-5889-895c-ca53cbdc7e2d")
    # Users
    # uuid.uuid5(FolioUUID.base_namespace, "users")
    users = uuid.UUID("dfe6e7b1-c0f5-5af1-b5e6-15344192fa79")
    # uuid.uuid5(FolioUUID.base_namespace, "permissions_user")
    permissions_users = uuid.UUID("ee483b0e-efc9-5f8b-a97a-d13a0af85e00")

    # Acquisitions
    # uuid.uuid5(FolioUUID.base_namespace, "orders")
    orders = uuid.UUID("2dc3e4fe-7a32-5014-afb1-099ee08d0626")
    # uuid.uuid5(FolioUUID.base_namespace, "po_lines")
    po_lines = uuid.UUID("c80f7071-83f9-5bc6-8cb6-289f15eb2cd9")
    # uuid.uuid5(FolioUUID.base_namespace, "organizations")
    organizations = uuid.UUID("576a4455-9024-5e46-bf22-b5737de15030")

    # ERM
    # ERM Does not honor generated UUIDs

    # Other
    # uuid.uuid5(FolioUUID.base_namespace, "other")
    other = uuid.UUID("d3a5076d-8bd0-570b-bf84-ee9cb5c4322e")
