# main.py
# ランチャー: UI を起動するだけの最小エントリーポイント

from __future__ import annotations

import sys

from downloader import setup_logging  # ロギング初期化（CTRL+C対応は downloader 側で有効化）
import ui


def main() -> None:
    logger = setup_logging()
    logger.info("yt-dlp-gui ランチャーを開始します (Python %s)", sys.version.split()[0])
    try:
        ui.main()
    except Exception:
        # ここで例外を握りつぶさずログを残して再送出
        logger.exception("UI 実行中に未処理の例外が発生しました")
        raise


if __name__ == "__main__":
    main()