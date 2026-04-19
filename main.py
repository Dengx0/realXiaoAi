from __future__ import annotations

import argparse
import logging

from xiaoi import AppConfig, run_http_server

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XiaoAI HTTP API entrypoint")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file. Defaults to config.json",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args()
    config = AppConfig.load(args.config)
    LOGGER.info("启动HTTP 服务，用于小爱音箱访问和播放生成的本地音效")
    run_http_server(config)


if __name__ == "__main__":
    main()
