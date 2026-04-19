import sys

from xiaoi import create_client_from_config


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    client = create_client_from_config(config_path)
    client.login()
    for device in client.get_devices():
        print(device.get("name"), device.get("deviceID"), device.get("miotDID"))


if __name__ == "__main__":
    main()
