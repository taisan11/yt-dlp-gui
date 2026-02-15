# downloader.py
# ダウンロード関連の処理とロギングを担うモジュール
# - UI 依存を排除し、コールバック（進捗・開始・完了・エラー）で通知
# - Ctrl+C(SIGINT) で全ダウンロードを中断できる仕組みを提供
# - yt-dlp の進捗フックで中断フラグを監視し安全に停止

from __future__ import annotations

import logging
import os
import signal
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yt_dlp

# =========================
# ロギング設定
# =========================

_DEFAULT_LOGGER_NAME = "yt_dlp_gui"
_LOGGER_INITIALIZED = False


def setup_logging(
    log_dir: Optional[Path | str] = None,
    level: int = logging.INFO,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """
    ロガーを初期化して返す。複数回呼んでも最初の設定を維持する。
    - log_dir が None の場合、カレントディレクトリ配下の 'logs' を使用
    - ログファイル: yt_dlp_gui.log（ローテーション）
    """
    global _LOGGER_INITIALIZED
    logger = logging.getLogger(_DEFAULT_LOGGER_NAME)

    if _LOGGER_INITIALIZED:
        return logger

    logger.setLevel(level)
    logger.propagate = False  # ルートロガーへ伝播させない

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)



    _LOGGER_INITIALIZED = True
    logger.debug("ロギング初期化完了")
    return logger


logger = setup_logging()


# =========================
# 例外
# =========================

class DownloadAborted(Exception):
    """ユーザ操作（停止/CTRL+C）などで中断されたことを示す例外。"""


# =========================
# SIGINT(CTRL+C) サポート
# =========================

# 登録された DownloadManager へブロードキャスト停止を行う
_registered_managers_lock = threading.Lock()
_registered_managers: List["DownloadManager"] = []


def _register_manager(mgr: "DownloadManager") -> None:
    with _registered_managers_lock:
        if mgr not in _registered_managers:
            _registered_managers.append(mgr)


def _unregister_manager(mgr: "DownloadManager") -> None:
    with _registered_managers_lock:
        if mgr in _registered_managers:
            _registered_managers.remove(mgr)


def _sigint_handler(signum, frame):
    logger.info("SIGINT(CTRL+C) 受信: 進行中のダウンロードを中断します")
    with _registered_managers_lock:
        for mgr in list(_registered_managers):
            try:
                mgr.stop()
            except Exception as e:
                logger.exception("中断処理中にエラー: %s", e)


def enable_ctrl_c_abort() -> None:
    """
    CTRL+C で全ての DownloadManager を中断するシグナルハンドラを設定。
    GUI（コンソール無し）環境では OS/ビルドにより効果がない場合があります。
    """
    try:
        signal.signal(signal.SIGINT, _sigint_handler)
        logger.debug("SIGINT(CTRL+C) ハンドラを設定しました")
    except Exception as e:
        logger.warning("SIGINT ハンドラの設定に失敗: %s", e)


# =========================
# コールバック型
# =========================

OnStart = Callable[[dict[str, Any]], None]
OnProgress = Callable[[dict[str, Any]], None]
OnComplete = Callable[[dict[str, Any]], None]
OnError = Callable[[dict[str, Any]], None]


@dataclass
class Callbacks:
    on_start: Optional[OnStart] = None
    on_progress: Optional[OnProgress] = None
    on_complete: Optional[OnComplete] = None
    on_error: Optional[OnError] = None


# =========================
# ユーティリティ
# =========================

def get_default_download_folder() -> Path:
    """
    OS に依らずホーム配下の Downloads を返す（存在しなくてもそのパスを返す）
    """
    home = Path.home()
    return home / "Downloads"


def _ensure_parent_dir(path: Path) -> None:
    try:
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("保存先ディレクトリの作成に失敗: %s (%s)", path, e)


def _to_outtmpl(path_or_tmpl: Path | str) -> str:
    """
    yt-dlp の outtmpl は文字列を要求。Path なら str に変換。
    """
    return str(path_or_tmpl)


# =========================
# ダウンロードマネージャ
# =========================

class DownloadManager:
    """
    yt-dlp を用いたダウンロード処理の管理クラス。
    - スレッドセーフな中断フラグ（abort_event）を保持
    - 進捗は yt-dlp の progress_hooks 経由で受け取り、コールバックへ転送
    """

    def __init__(self, cookie_file: Optional[str | Path] = None) -> None:
        self.cookie_file: Optional[Path] = Path(cookie_file) if cookie_file else None
        self.abort_event = threading.Event()
        self._lock = threading.RLock()
        self._active = False  # 進行中フラグ
        _register_manager(self)

    def __del__(self) -> None:
        _unregister_manager(self)


    def set_cookie_file(self, cookie_file: Optional[str | Path]) -> None:

        with self._lock:

            self.cookie_file = Path(cookie_file) if cookie_file else None



    def set_metadata_mode(self, mode: str) -> None:

        """

        メタデータの扱いを設定する。
        - "embed": 動画/音声ファイルへメタデータを埋め込む（デフォルト）
        - "separate": .info.json のサイドカーとして保存
        - "none": 何もしない
        """
        normalized = (mode or "").strip().lower()
        if normalized not in ("embed", "separate", "none"):
            normalized = "embed"
        with self._lock:
            setattr(self, "metadata_mode", normalized)

    def stop(self) -> None:
        """
        進行中のダウンロードを中断する。

        """

        self.abort_event.set()

        logger.info("中断フラグを設定しました")


    # ---------- 基本的な情報取得 ----------

    def fetch_info(self, url: str) -> dict[str, Any]:  # type: ignore[name-defined]
        """
        URL のメタ情報(タイトル、ライブフラグ、利用可能フォーマット等)を取得。
        """
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "outtmpl": "%(title)s.%(ext)s",
        }
        if self.cookie_file and self.cookie_file.exists():
            ydl_opts["cookiefile"] = str(self.cookie_file)

        logger.debug("情報取得を開始: %s", url)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                info = ydl.extract_info(url, download=False) or {}  # type: ignore[return-value]
            logger.debug("情報取得完了: title=%s is_live=%s", info.get("title"), info.get("is_live"))
            return info  # type: ignore[return-value]
        except Exception as e:
            logger.exception("情報取得に失敗: %s", e)
            raise

    # ---------- ダウンロード実行 ----------
    def _progress_hook_factory(self, callbacks: Callbacks) -> Callable[[dict[str, Any]], None]:
        def _hook(d: dict[str, Any]) -> None:
            # 中断要求があれば例外で停止させる
            if self.abort_event.is_set():
                raise DownloadAborted("ユーザにより中断されました")
            # 進捗イベント転送
            if callbacks.on_progress:
                try:
                    callbacks.on_progress(d)
                except Exception:
                    logger.exception("on_progress コールバック内で例外")
        return _hook

    def _build_ydl_opts(
        self,
        format_str: str,
        outtmpl: str,
        callbacks: Callbacks,
        is_live: bool = False,
        live_from_start: bool = True,
        metadata_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        ydl_opts = {
            "format": format_str,
            "outtmpl": outtmpl,
            "progress_hooks": [self._progress_hook_factory(callbacks)],
            # 安定性向上の推奨オプション
            "retries": 10,
            # 重複ファイル名の処理: _1, _2, ... と自動的にカウントアップ
            "overwrites": False,
            "nooverwrites": True,
        }

        # ライブ向け設定
        if is_live:
            ydl_opts.update(
                {
                    "live_from_start": live_from_start,
                    "wait_for_video": (5, 10),
                    "concurrent_fragment_downloads": 5,
                }
            )


        if self.cookie_file and self.cookie_file.exists():

            ydl_opts["cookiefile"] = str(self.cookie_file)



        # メタデータの扱い（デフォルトは埋め込み）
        mode = (metadata_mode or getattr(self, "metadata_mode", "embed") or "embed").strip().lower()
        if mode == "embed":
            ydl_opts["addmetadata"] = True
        elif mode == "separate":
            ydl_opts["writeinfojson"] = True
        # "none" は何もしない

        return ydl_opts


    def _run_download(self, ydl_opts: dict[str, Any], url: str, callbacks: Callbacks) -> None:
        """
        yt-dlp の download 実行ラッパ。開始・完了・エラーのコールバックをハンドル。
        """
        with self._lock:
            self.abort_event.clear()
            self._active = True

        if callbacks.on_start:
            try:
                callbacks.on_start({"url": url})
            except Exception:
                logger.exception("on_start コールバック内で例外")

        logger.info("ダウンロード開始: %s", url)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                ydl.download([url])
        except DownloadAborted as e:
            logger.info("ダウンロードが中断されました: %s", e)
            if callbacks.on_error:
                try:
                    callbacks.on_error({"url": url, "error": str(e), "aborted": True})
                except Exception:
                    logger.exception("on_error コールバック内で例外")
            raise
        except KeyboardInterrupt:
            # メインスレッドに SIGINT が来た場合の保険
            logger.info("KeyboardInterrupt によりダウンロード中断")
            self.abort_event.set()
            if callbacks.on_error:
                try:
                    callbacks.on_error({"url": url, "error": "KeyboardInterrupt", "aborted": True})
                except Exception:
                    logger.exception("on_error コールバック内で例外")
            raise DownloadAborted("KeyboardInterrupt")
        except Exception as e:
            logger.exception("ダウンロード中にエラー: %s", e)
            if callbacks.on_error:
                try:
                    callbacks.on_error({"url": url, "error": str(e)})
                except Exception:
                    logger.exception("on_error コールバック内で例外")
            raise
        else:
            logger.info("ダウンロード完了: %s", url)
            if callbacks.on_complete:
                try:
                    callbacks.on_complete({"url": url})
                except Exception:
                    logger.exception("on_complete コールバック内で例外")
        finally:
            with self._lock:
                self._active = False

    # 公開メソッド群

    def download_video(
        self,
        url: str,
        format_id_or_expr: str,
        save_path_or_tmpl: str | Path,
        callbacks: Optional[Callbacks] = None,
        is_livestream: bool = False,
        live_from_start: bool = True,
        single_file_mode: bool = True,
        metadata_mode: Optional[str] = None,
    ) -> None:
        """
        単一動画/配信のダウンロード。
        - format_id_or_expr: 例 "137+140" や "bestvideo+bestaudio/best"
        - save_path_or_tmpl:
            single_file_mode=True の場合は完全なファイルパスのテンプレ（例: "C:/foo/bar/%(title)s.%(ext)s" も可）
            single_file_mode=False の場合はディレクトリを指定し、"%(title)s.%(ext)s" を自動付与
        """
        callbacks = callbacks or Callbacks()

        # outtmpl を決める
        if single_file_mode:
            outtmpl = _to_outtmpl(save_path_or_tmpl)
            _ensure_parent_dir(Path(outtmpl))
        else:
            outdir = Path(save_path_or_tmpl)
            _ensure_parent_dir(outdir / "dummy")
            outtmpl = _to_outtmpl(outdir / "%(title)s.%(ext)s")

        ydl_opts = self._build_ydl_opts(
            format_str=format_id_or_expr,
            outtmpl=outtmpl,
            callbacks=callbacks,
            is_live=is_livestream,
            live_from_start=live_from_start,
            metadata_mode=metadata_mode,
        )
        self._run_download(ydl_opts, url, callbacks)

    def download_livestream(
        self,
        url: str,
        format_id_or_expr: str,
        save_path_or_tmpl: str | Path,
        callbacks: Optional[Callbacks] = None,
        live_from_start: bool = True,
        single_file_mode: bool = True,
        metadata_mode: Optional[str] = None,
    ) -> None:
        """
        生配信のダウンロードを明示的に行いたい場合のラッパ。
        """
        self.download_video(
            url=url,
            format_id_or_expr=format_id_or_expr,
            save_path_or_tmpl=save_path_or_tmpl,
            callbacks=callbacks,
            is_livestream=True,
            live_from_start=live_from_start,
            single_file_mode=single_file_mode,
            metadata_mode=metadata_mode,
        )

    def download_url_list(
        self,
        url_list_path: str | Path,
        format_expr: str,
        save_dir: str | Path,
        callbacks: Optional[Callbacks] = None,
        per_item_callbacks_factory: Optional[Callable[[str], Callbacks]] = None,
        metadata_mode: Optional[str] = None,
    ) -> None:
        """
        URL リストファイルを読み取り、1 行ずつダウンロードする。
        - per_item_callbacks_factory が指定されている場合は URL ごとに個別のコールバックを生成可能
        """
        callbacks = callbacks or Callbacks()
        file_path = Path(url_list_path)
        save_dir = Path(save_dir)
        _ensure_parent_dir(save_dir / "dummy")

        # 全体開始
        if callbacks.on_start:
            try:
                callbacks.on_start({"url_list_path": str(file_path)})
            except Exception:
                logger.exception("on_start コールバック内で例外")

        try:
            urls: List[str] = []
            with file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    u = line.strip()
                    if u:
                        urls.append(u)
        except Exception as e:
            logger.exception("URL リストの読み込みに失敗: %s", e)
            if callbacks.on_error:
                try:
                    callbacks.on_error({"error": str(e), "phase": "read_url_list"})
                except Exception:
                    logger.exception("on_error コールバック内で例外")
            raise

        total = len(urls)
        logger.info("連続ダウンロード開始: %d 件", total)

        for idx, url in enumerate(urls, 1):
            if self.abort_event.is_set():
                logger.info("連続ダウンロードが中断されました (開始前判定)")
                raise DownloadAborted("ユーザにより中断されました")

            # 進捗通知（全体）
            if callbacks.on_progress:
                try:
                    callbacks.on_progress({"current": idx, "total": total, "url": url})
                except Exception:
                    logger.exception("on_progress コールバック内で例外")

            item_callbacks = (
                per_item_callbacks_factory(url) if per_item_callbacks_factory else Callbacks()
            )
            try:
                outtmpl = _to_outtmpl(save_dir / "%(title)s.%(ext)s")
                ydl_opts = self._build_ydl_opts(
                    format_str=format_expr,
                    outtmpl=outtmpl,
                    callbacks=item_callbacks,
                    is_live=False,
                    metadata_mode=metadata_mode,
                )
                self._run_download(ydl_opts, url, item_callbacks)
            except DownloadAborted:
                logger.info("連続ダウンロードが中断されました (項目 %d/%d)", idx, total)
                raise
            except Exception as e:
                logger.exception("URL(%d/%d) のダウンロード失敗: %s", idx, total, e)
                # 全体のエラー通知
                if callbacks.on_error:
                    try:
                        callbacks.on_error({"current": idx, "total": total, "url": url, "error": str(e)})
                    except Exception:
                        logger.exception("on_error コールバック内で例外")
                # 続行
                continue

        # 全体完了
        if callbacks.on_complete:
            try:
                callbacks.on_complete({"total": total})
            except Exception:
                logger.exception("on_complete コールバック内で例外")

    def download_playlist_simple(
        self,
        url: str,
        format_expr: str,
        save_dir: str | Path,
        callbacks: Optional[Callbacks] = None,
        metadata_mode: Optional[str] = None,
    ) -> None:
        """
        単純なプレイリスト/チャンネル URL のダウンロード。
        - 出力テンプレは「%(playlist_index)s - %(title)s.%(ext)s」を優先的に採用
        """
        callbacks = callbacks or Callbacks()
        save_dir = Path(save_dir)
        _ensure_parent_dir(save_dir / "dummy")

        # プレイリスト検知は yt-dlp 側に委ねてもよいが、簡易的にプレフィクスで決める
        is_playlist_like = any(key in url for key in ("playlist", "channel"))
        base_template = "%(playlist_index)s - %(title)s.%(ext)s" if is_playlist_like else "%(title)s.%(ext)s"
        outtmpl = _to_outtmpl(save_dir / base_template)

        ydl_opts = self._build_ydl_opts(
            format_str=format_expr,
            outtmpl=outtmpl,
            callbacks=callbacks,
            is_live=False,
            metadata_mode=metadata_mode,
        )
        self._run_download(ydl_opts, url, callbacks)


# =========================
# フォーマットユーティリティ（UI で使える軽量情報）
# =========================

def build_format_list_from_info(info: dict[str, Any]) -> list[str]:
    """
    extract_info の返却から UI 向けフォーマット一覧(文字列)を生成。
    "id - 720p (mp4) 50.1MB" のような形。
    """
    formats = []
    for f in info.get("formats", []) or []:
        try:
            parts: list[str] = [str(f.get("format_id", "")), "-"]
            res = f.get("resolution") or ""
            if res:
                parts.append(str(res))
            ext = f.get("ext") or ""
            if ext:
                parts.append(f"({ext})")
            size = f.get("filesize")
            if not size:
                size = f.get("filesize_approx")
            if size:
                size_mb = float(size) / (1024 * 1024)
                parts.append(f"{size_mb:.1f}MB")
            formats.append(" ".join([p for p in parts if p]))
        except Exception:
            # 1件壊れていても全体は続行
            continue
    return formats


# =========================
# モジュール初期化
# =========================

# デフォルトで CTRL+C を有効化（コンソール実行時に有効）
# GUI バンドル（コンソール無し）では効果が限定的な場合があります
try:
    enable_ctrl_c_abort()
except Exception:
    # 失敗しても致命的ではない
    pass