import sys

from xiaoi import create_client_from_config


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    client = create_client_from_config(config_path)
    client.login()
    device = client.ensure_device()
    print(device["name"])


if __name__ == "__main__":
    main()
