import argparse
from folioclient.FolioClient import FolioClient
import datetime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("okapi_url", help=("OKAPI base url"))
    parser.add_argument("tenant_id", help=("id of the FOLIO tenant."))
    parser.add_argument("username", help=("the api user"))
    parser.add_argument("password", help=("the api users password"))
    args = parser.parse_args()
    print("\tOkapi URL:\t", args.okapi_url)
    print("\tTenanti Id:\t", args.tenant_id)
    print("\tUsername:\t", args.username)
    print("\tPassword:\tSecret")
    folio_client = FolioClient(
        args.okapi_url, args.tenant_id, args.username, args.password
    )
    print(f"Found {len(folio_client.locations)} locations")
    item_loan_types = folio_client.get_all_ids("/loan-types")
    print(f"Fetched {len(item_loan_types)} item loan types")
    random_users = folio_client.get_random_objects("/users", 10, "")
    print(f"Fetched {len(random_users)} random users")
    print(folio_client.current_user)
    print(folio_client.get_metadata_construct())
    print(len(folio_client.folio_get_all("/circulation/requests")))
    print(list(t["name"] for t in folio_client.alt_title_types))
    print(
        list(
            t["name"]
            for t in folio_client.folio_get_all(
                "/alternative-title-types", "alternativeTitleTypes"
            )
        )
    )

    df = "%Y-%m-%dT%H:%M:%S.%f+0000"

    """bc = {
        "userBarcode": "6366520002522045",
        "itemBarcode": "32356000869907",
        "servicePointId": "83d474aa-ee99-4924-8704-a03e3c56e0d9",
    }
    loan = folio_client.check_out_by_barcode(
        bc["itemBarcode"],
        bc["userBarcode"],
        datetime.datetime.now(),
        bc["servicePointId"],
    )
    if loan:
        folio_client.extend_open_loan(
            loan[1], datetime.datetime.now(), datetime.datetime.now()
        )"""


if __name__ == "__main__":
    main()
