import uuid

from folio_uuid.folio_namespaces import FOLIONamespaces


class FolioUUID(uuid.UUID):
    """handles communication and getting values from FOLIO"""

    base_namespace = uuid.UUID("8405ae4d-b315-42e1-918a-d1919900cf3f")

    def __init__(
        self, tenant_id: str, folio_object_type: FOLIONamespaces, legacy_identifier: str
    ):
        """
        Create a deterministic UUID for a FOLIO tenant

        Parameters
        ----------
        tenant_id : str
            The tenant id (or other tenant string)
        folio_object_type : FOLIONamespaces
            Enum helping to avoid collisions within a tenant.
        legacy_identifier : str
            The actual identifier from the legacy system
        """
        u = uuid.uuid5(folio_object_type.value, f"{tenant_id}:{legacy_identifier}")
        super(FolioUUID, self).__init__(str(u))
