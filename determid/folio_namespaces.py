import uuid
import enum


class FOLIONamespaces(enum.Enum):

    # Inventory
    # uuid.uuid5(namespace, "holdings")
    holdings = uuid.UUID("81b6a778-b024-5050-9712-81d01c2ee33b")
    # uuid.uuid5(namespace, "items")
    items = uuid.UUID("4ccaf819-a366-55f2-9a99-4e37f8d4031b")
    # uuid.uuid5(namespace, "instances")
    instances = uuid.UUID("09d734f7-d5df-5fa1-9b5e-31d34f4bcfef")

    # SRS
    # uuid.uuid5(namespace, "srs_records")
    srs_records = uuid.UUID("13e60b21-777c-5cb6-b7d8-2855b5d41852")
    # uuid.uuid5(namespace, "raw_records")
    raw_records = uuid.UUID("cd2ba9c1-bb21-5148-8a39-3190fd78a047")
    # uuid.uuid5(namespace, "parsed_records")
    parsed_records = uuid.UUID("9857b7bc-569c-53e4-bb1f-5449f8c4f62b")

    # Users
    # uuid.uuid5(namespace, "users")
    users = uuid.UUID("dfe6e7b1-c0f5-5af1-b5e6-15344192fa79")
    # uuid.uuid5(namespace, "permissions_user")
    permissions_users = uuid.UUID("ee483b0e-efc9-5f8b-a97a-d13a0af85e00")

    # Acquisitions
    # uuid.uuid5(namespace, "orders")
    orders = uuid.UUID("2dc3e4fe-7a32-5014-afb1-099ee08d0626")
    # uuid.uuid5(namespace, "organizations")
    organizations = uuid.UUID("576a4455-9024-5e46-bf22-b5737de15030")

    # Other
    # uuid.uuid5(namespace, "other")
    other = uuid.UUID("d3a5076d-8bd0-570b-bf84-ee9cb5c4322e")
