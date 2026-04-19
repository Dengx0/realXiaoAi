import time
import sys

from xiaoi import create_client_from_config
from xiaoi.messages import XiaoAiMessagePoller


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    client = create_client_from_config(config_path)
    poller = XiaoAiMessagePoller(client)
    while True:
        message = poller.fetch_next_message()
        if message:
            print(message.timestamp, message.query)
        time.sleep(2)


if __name__ == "__main__":
    main()
