import uuid
import math
import re

from folio_uuid.folio_namespaces import FOLIONamespaces


class FolioUUID(uuid.UUID):
    """Creates deterministic UUIDs for FOLIO"""

    base_namespace = uuid.UUID("8405ae4d-b315-42e1-918a-d1919900cf3f")

    def __init__(
        self, okapi_url: str, folio_object_type: FOLIONamespaces, legacy_identifier: str
    ):
        """
        Create a deterministic UUID for a FOLIO tenant

        Parameters
        ----------
        okapi_url : str
            The tenant id (or other tenant string)
        folio_object_type : FOLIONamespaces
            Enum helping to avoid collisions within a tenant.
        legacy_identifier : str
            The actual identifier from the legacy system
        """
        clean_id = self.clean_iii_identifiers(legacy_identifier)
        u = uuid.uuid5(folio_object_type.value, f"{okapi_url}:{clean_id}")
        super(FolioUUID, self).__init__(str(u))

    @staticmethod
    def calculate_sierra_check_digit(record_number: int) -> str:
        """Rewritten to python from https://github.com/SydneyUniLibrary/sierra-record-check-digit/blob/master/index.js"""
        m = 2
        x = 0
        i = record_number
        while i > 0:
            a = i % 10
            i = math.floor(i / 10)
            x += a * m
            m += 1
        r = x % 11
        return "x" if r == 10 else str(r)

    @staticmethod
    def clean_iii_identifiers(identifier: str) -> str:
        """
        Cleans potential III/SIERRA/Millennium Identifiers from noise like
        the dot (.) and check digits and potential other things at
        the end of the strings. All other types of identifiers
        should just run through.

        Parameters
        ----------
        identifier : str
            An identifier of any kind.

        """
        reg_pattern = r"^(\.?[bcoiv]?)([0-9xX]{6,8})(@\w{1,5})?$"
        match = re.search(reg_pattern, identifier)
        if not match or not match[1]:  # No match, no III id
            return identifier
        fore = match[1]
        number_part = match[2]
        if len(number_part) > 6:
            # Aft  is reachable by aft = match[3]
            last_char = number_part[-1]
            nums = int(number_part[:-1])
            if FolioUUID.calculate_sierra_check_digit(nums) == last_char:
                return f"{fore.replace('.','')}{nums}"
            else:
                return f"{fore.replace('.','')}{number_part}"
        elif len(number_part) == 6:
            return f"{fore.replace('.','')}{number_part}"
        else:
            return identifier
