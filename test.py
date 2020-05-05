import argparse
from folioclient.FolioClient import FolioClient


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


if __name__ == "__main__":
    main()
