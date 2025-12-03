# ui.py
# TkEasyGUI ベースの UI 実装。downloader モジュールを利用して
# - 単一動画/生配信のダウンロード
# - URL リスト/プレイリストの連続ダウンロード（停止ボタン付き）
# - 設定の保存/読込（settings.json）
# - バージョン表示（設定タブ）
#
# 本 UI は downloader.DownloadManager のコールバック経由でイベントを受け取り、
# それを画面に反映する。

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional, cast

import TkEasyGUI as eg

from downloader import (
    Callbacks,
    DownloadAborted,
    DownloadManager,
    build_format_list_from_info,
    get_default_download_folder,
    setup_logging,
)

logger = setup_logging()

# 設定ファイル
SETTINGS_PATH = Path("settings.json")


# -----------------------------
# 設定とバージョン
# -----------------------------
def load_settings() -> Dict[str, Any]:
    try:
        if SETTINGS_PATH.exists():
            with SETTINGS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f) or {}
                if isinstance(data, dict):
                    return data
    except Exception as e:
        logger.debug(f"設定読込エラー: {e}")
    return {}


def save_settings(data: Dict[str, Any]) -> None:
    try:
        with SETTINGS_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"設定保存エラー: {e}")


def compute_versions() -> Dict[str, str]:
    versions: Dict[str, str] = {}
    try:
        versions["python"] = sys.version.split()[0]
    except Exception:
        versions["python"] = "unknown"
    try:
        import yt_dlp  # type: ignore
        versions["yt_dlp"] = getattr(yt_dlp, "__version__", "unknown")
    except Exception:
        versions["yt_dlp"] = "unknown"
    try:
        versions["tkeasygui"] = getattr(eg, "__version__", "unknown")
    except Exception:
        versions["tkeasygui"] = "unknown"
    return versions


# -----------------------------
# ユーティリティ
# -----------------------------
def run_in_thread(target, *args, **kwargs) -> None:
    t = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    t.start()


def safe_filename(name: str) -> str:
    keep = (" ", "-", "_", ".")
    return "".join(c for c in name if c.isalnum() or c in keep).rstrip()


def parse_selected_format_id(selected: str) -> str:
    # "id - 720p (mp4) 50MB" -> "id"
    return (selected or "").split(" - ")[0].strip()


# -----------------------------
# スレッドワーカ（情報取得）
# -----------------------------
def worker_fetch_video_info(manager: DownloadManager, url: str, window: eg.Window) -> None:
    try:
        info = manager.fetch_info(url)
        if not info:
            window.post_event("--VIDEO-INFO-ERROR--", {"error": "情報が取得できませんでした"})
            return

        title = info.get("title") or ""
        if bool(info.get("is_live", False)):
            window.post_event("--VIDEO-INFO-LIVE--", {"title": title, "url": url})
            return

        formats = build_format_list_from_info(info)
        window.post_event("--VIDEO-INFO-READY--", {"title": title, "formats": formats})
    except Exception as e:
        logger.exception("動画情報取得に失敗")
        window.post_event("--VIDEO-INFO-ERROR--", {"error": str(e)})


def worker_fetch_live_info(manager: DownloadManager, url: str, window: eg.Window) -> None:
    try:
        info = manager.fetch_info(url)
        if not info:
            window.post_event("--LIVE-INFO-ERROR--", {"error": "情報が取得できませんでした"})
            return

        title = info.get("title") or ""
        if not bool(info.get("is_live", False)):
            window.post_event("--LIVE-INFO-ERROR--", {"error": "この URL は生配信ではありません"})
            return

        formats = build_format_list_from_info(info)
        window.post_event("--LIVE-INFO-READY--", {"title": title, "formats": formats})
    except Exception as e:
        logger.exception("生配信情報取得に失敗")
        window.post_event("--LIVE-INFO-ERROR--", {"error": str(e)})


# -----------------------------
# スレッドワーカ（ダウンロード）
# -----------------------------
def _callbacks_single(window: eg.Window) -> Callbacks:
    return Callbacks(
        on_start=lambda ctx: window.post_event("--DOWNLOAD-START--", {}),
        on_progress=lambda d: window.post_event("--DOWNLOAD-PROGRESS--", cast(Dict[Any, Any], d)),
        on_complete=lambda ctx: window.post_event("--DOWNLOAD-COMPLETE--", {}),
        on_error=lambda ctx: window.post_event("--DOWNLOAD-ERROR--", cast(Dict[Any, Any], {"error": ctx.get("error", "")})),
    )


def _callbacks_live(window: eg.Window) -> Callbacks:
    return Callbacks(
        on_start=lambda ctx: window.post_event("--LIVE-DOWNLOAD-START--", {}),
        on_progress=lambda d: window.post_event("--LIVE-DOWNLOAD-PROGRESS--", cast(Dict[Any, Any], d)),
        on_complete=lambda ctx: window.post_event("--LIVE-DOWNLOAD-COMPLETE--", {}),
        on_error=lambda ctx: window.post_event("--LIVE-DOWNLOAD-ERROR--", cast(Dict[Any, Any], {"error": ctx.get("error", "")})),
    )


def _callbacks_playlist(window: eg.Window) -> Callbacks:
    return Callbacks(
        on_progress=lambda d: window.post_event("--RENZOKU-PROGRESS--", cast(Dict[Any, Any], d)),
        on_complete=lambda ctx: window.post_event("--RENZOKU-DOWNLOAD-COMPLETE--", {}),
        on_error=lambda ctx: window.post_event("--RENZOKU-DOWNLOAD-ERROR--", cast(Dict[Any, Any], {"error": ctx.get("error", "")})),
    )



def worker_download_single(

    manager: DownloadManager,

    url: str,

    format_id: str,

    save_path: str,

    window: eg.Window,

    metadata_mode: Optional[str] = None,
    is_livestream: bool = False,

    live_from_start: bool = True,

) -> None:

    callbacks = _callbacks_live(window) if is_livestream else _callbacks_single(window)
    try:
        if is_livestream:
            manager.download_livestream(
                url=url,
                format_id_or_expr=format_id,
                save_path_or_tmpl=save_path,
                callbacks=callbacks,
                live_from_start=live_from_start,
                single_file_mode=True,
            )
        else:

                        manager.download_video(

                            url=url,

                            format_id_or_expr=format_id,

                            save_path_or_tmpl=save_path,

                            callbacks=callbacks,

                            is_livestream=False,

                            live_from_start=True,

                            single_file_mode=True,

                            metadata_mode=metadata_mode,
                        )

    except DownloadAborted:
        logger.info("ダウンロードはユーザにより中断されました")
    except Exception as e:
        logger.exception("単一ダウンロードに失敗")
        if is_livestream:
            window.post_event("--LIVE-DOWNLOAD-ERROR--", {"error": str(e)})
        else:
            window.post_event("--DOWNLOAD-ERROR--", {"error": str(e)})



def worker_download_url_list(

    manager: DownloadManager,

    url_list_path: str,

    format_expr: str,

    save_dir: str,

    metadata_mode: Optional[str],
    window: eg.Window,

) -> None:

    # 事前カウント
    total = 0
    try:
        with open(url_list_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    total += 1
    except Exception as e:
        logger.exception("URL リスト読み込みに失敗（事前カウント）")
        window.post_event("--URL-LIST-FILE-ERROR--", cast(Dict[Any, Any], {"error": str(e)}))
        return

    window.post_event("--URL-LIST-START--", cast(Dict[Any, Any], {"total": total}))

    def all_callbacks() -> Callbacks:
        return Callbacks(
            on_progress=lambda d: window.post_event("--URL-LIST-PROGRESS--", cast(Dict[Any, Any], d)),
            on_complete=lambda ctx: window.post_event("--URL-LIST-COMPLETE--", cast(Dict[Any, Any], {"total": ctx.get("total", total)})),
            on_error=lambda ctx: window.post_event("--URL-LIST-ERROR--", cast(Dict[Any, Any], ctx)),
        )

    def per_item_factory(url: str) -> Callbacks:
        return Callbacks(on_progress=lambda d: window.post_event("--RENZOKU-PROGRESS--", cast(Dict[Any, Any], d)))


        manager.download_url_list(

            url_list_path=url_list_path,

            format_expr=format_expr,

            save_dir=save_dir,

            callbacks=all_callbacks(),

            per_item_callbacks_factory=per_item_factory,

            metadata_mode=metadata_mode,
        )
        try:
            manager.download_url_list(
                url_list_path=url_list_path,
                format_expr=format_expr,
                save_dir=save_dir,
                callbacks=all_callbacks(),
                per_item_callbacks_factory=per_item_factory,
                metadata_mode=metadata_mode,
            )
        except DownloadAborted:
            logger.info("URL リストの処理は中断されました")
        except Exception as e:
            logger.exception("URL リスト処理中に失敗")
            window.post_event("--URL-LIST-FILE-ERROR--", {"error": str(e)})



def worker_download_playlist(

    manager: DownloadManager,

    url: str,

    format_expr: str,

    save_dir: str,

    metadata_mode: Optional[str],
    window: eg.Window,

) -> None:

    callbacks = _callbacks_playlist(window)
    try:
        manager.download_playlist_simple(url=url, format_expr=format_expr, save_dir=save_dir, callbacks=callbacks)
    except DownloadAborted:
        logger.info("プレイリスト処理は中断されました")
    except Exception as e:
        logger.exception("プレイリスト処理中に失敗")
        window.post_event("--RENZOKU-DOWNLOAD-ERROR--", {"error": str(e)})



def build_layout(settings: Dict[str, Any]) -> list[list[Any]]:

    cookie_init = settings.get("cookie_list", "")

    renzoku_folder_init = settings.get("renzoku_folder", "")

    save_path_init = settings.get("save_path", "")

    live_save_path_init = settings.get("live_save_path", "")

    filename_template_init = settings.get("filename_template", "%(title)s.%(ext)s")

    metadata_mode_init = settings.get("metadata_mode", "embed")



    layout_live = [

        [eg.Text("生配信ダウンロード!!", font=("Helvetica", 13, "bold"))],
        [eg.Text("生配信URL:"), eg.InputText("", key="live_url"), eg.Button("生配信情報取得")],
        [eg.Combo(values=[], key="live_formats", size=(40, 10))],
        [eg.Text("ダウンロードオプション:")],
        [eg.Radio("配信開始からダウンロード", "live_option", key="live_from_start", default=True)],
        [eg.Radio("現在の位置からダウンロード", "live_option", key="live_from_now")],
        [eg.Text("保存先:"), eg.InputText(live_save_path_init, key="live_save_path"), eg.FileSaveAs("ファイル保存先")],
        [eg.Button("生配信ダウンロード開始"), eg.Button("生配信ダウンロード停止", key="live_stop")],
        [eg.Text("情報")],
        [eg.Text("", key="live_title")],
        [eg.Text("", key="live_status")],
    ]

    layout_renzoku = [
        [eg.Text("連続ダウンロード!!", font=("Helvetica", 13, "bold"))],
        [eg.Text("URLリストファイルまたはプレイリストURL:"), eg.InputText("", key="url_input"), eg.FileBrowse("URLリスト")],
        [eg.Text("出力形式:"), eg.Radio("video", "AV", default=True, key="renzoku_video"), eg.Radio("audio", "AV", key="renzoku_audio")],
        [eg.Text("保存フォルダ:"), eg.InputText(renzoku_folder_init, key="renzoku_folder"), eg.FolderBrowse("フォルダ選択")],
        [eg.Button("連続ダウンロード開始"), eg.Button("連続ダウンロード停止", key="renzoku_stop")],
        [eg.Text("", key="renzoku_status")],
    ]

    layout_main = [
        [eg.Text("動画とかダウンローダー", font=("Helvetica", 20))],
        [eg.Text("単一動画ダウンロード!!", font=("Helvetica", 13, "bold"))],
        [eg.Text("URL:"), eg.InputText("", key="url"), eg.Button("さらなる情報を取得")],
        [eg.Combo(values=["bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best", "bestaudio[ext=webm]"], default_value="bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best",key="list", size=(40, 10))],
        [eg.Text("保存設定", font=("Helvetica", 13, "bold"))],
        [eg.Text("保存先:"), eg.InputText(default_text=str(get_default_download_folder()), key="save_path"), eg.FolderBrowse("ファイル保存先")],
        [eg.Button("単一ダウンロード開始")],
        [eg.Text("情報")],
        [eg.Text("", key="title")],
        [eg.Text("", key="status")],
    ]


    layout_settings = [

        [eg.Text("設定", font=("Helvetica", 20))],


        [eg.Text("CookieList:"), eg.InputText(cookie_init, key="cookie_list"), eg.FileBrowse("選択")],

        [eg.Text("ファイル名テンプレート:"), eg.InputText(filename_template_init, key="filename_template")],

        [eg.Text("メタデータ出力:")],
        [eg.Radio("埋め込み", "metadata_option", key="metadata_embed", default=(metadata_mode_init == "embed"))],
        [eg.Radio("別ファイル(.info.json)", "metadata_option", key="metadata_separate", default=(metadata_mode_init == "separate"))],
        [eg.Radio("なし", "metadata_option", key="metadata_none", default=(metadata_mode_init == "none"))],
        [eg.Text("バージョン情報", font=("Helvetica", 13, "bold"))],

        [eg.Text("", key="ver_app")],
        [eg.Text("", key="ver_python")],
        [eg.Text("", key="ver_ytdlp")],
        [eg.Text("", key="ver_tkeasygui")],
        [eg.Button("説明書を開く")],
    ]

    layout = [
        [
            eg.TabGroup(
                [
                    [
                        eg.Tab("一般", layout_main),
                        eg.Tab("生配信", layout_live),
                        eg.Tab("連続", layout_renzoku),
                        eg.Tab("設定", layout_settings),
                    ]
                ]
            )
        ],
    ]
    return layout


# -----------------------------
# メイン
# -----------------------------
def main() -> None:
    manager = DownloadManager()
    settings = load_settings()
    layout = build_layout(settings)

    with eg.Window("ようつべだうろだ", layout, resizable=True) as window:
        # バージョン表示
        vers = compute_versions()
        try:
            window["ver_app"].update("App: yt-dlp-gui")
            window["ver_python"].update(f"Python: {vers.get('python', '')}")
            window["ver_ytdlp"].update(f"yt-dlp: {vers.get('yt_dlp', '')}")
            window["ver_tkeasygui"].update(f"TkEasyGUI: {vers.get('tkeasygui', '')}")
        except Exception:
            pass

        # SIGINT handler: stop and request app exit
        try:
            def _on_sigint(signum, frame):
                manager.stop()
                try:
                    window.post_event("--APP-EXIT--", {})
                except Exception:
                    pass

            signal.signal(signal.SIGINT, _on_sigint)
        except Exception:
            logger.debug("SIGINT handler not set")

        for event, values in window.event_iter():
            values = values or {}


            if event in (eg.WIN_CLOSED, "--APP-EXIT--"):

                save_settings(

                    {

                        "cookie_list": values.get("cookie_list", "") or "",

                        "renzoku_folder": values.get("renzoku_folder", "") or "",

                        "save_path": values.get("save_path", "") or "",


                        "live_save_path": values.get("live_save_path", "") or "",

                        "filename_template": values.get("filename_template", "") or "",

                        "metadata_mode": ("embed" if values.get("metadata_embed") else ("separate" if values.get("metadata_separate") else ("none" if values.get("metadata_none") else "embed"))),
                    }

                )
                manager.stop()

                break



            # 設定（Cookie/メタデータ 反映）

            manager.set_cookie_file(values.get("cookie_list") or None)
            mode = "embed" if values.get("metadata_embed") else ("separate" if values.get("metadata_separate") else ("none" if values.get("metadata_none") else "embed"))
            manager.set_metadata_mode(mode)


            # ------------- 一般（単一動画） -------------
            if event == "さらなる情報を取得":
                url = (values.get("url") or "").strip()
                if not url:
                    window["status"].update("URLを入力してください")
                    continue
                window["status"].update("情報取得中...")
                run_in_thread(worker_fetch_video_info, manager, url, window)

            elif event == "単一ダウンロード開始":
                url = (values.get("url") or "").strip()
                if not url:
                    window["status"].update("URLを入力してください")
                    continue

                selected_format = values.get("list") or ""
                if not selected_format:
                    window["status"].update("フォーマットを選択してください")
                    continue


                save_folder = values.get("save_path") or ""

                if not save_folder:
                    window["status"].update("保存フォルダを選択してください")

                    continue

                tmpl = values.get("filename_template") or settings.get("filename_template", "%(title)s.%(ext)s")
                outtmpl = str(Path(save_folder) / tmpl)

                format_id = parse_selected_format_id(selected_format)

                window["status"].update("ダウンロード開始...")

                run_in_thread(

                    worker_download_single,

                    manager,

                    url,

                    format_id,


                    outtmpl,

                    window,

                    mode,

                    False,


                    True,

                )


            # 情報取得結果の反映
            elif event == "--VIDEO-INFO-READY--":
                window["title"].update(values.get("title", ""))
                window["list"].update(values=values.get("formats", []))
                window["status"].update("情報取得完了")
                title = values.get("title")



            elif event == "--VIDEO-INFO-LIVE--":
                window["title"].update(values.get("title", ""))
                window["status"].update("この URL は生配信です。生配信タブで処理してください。")
                if values.get("url"):
                    window["live_url"].update(values["url"])

            elif event == "--VIDEO-INFO-ERROR--":
                window["title"].update("エラー")
                window["status"].update(f"情報取得エラー: {values.get('error', '')}")

            elif event == "--DOWNLOAD-START--":
                window["status"].update("ダウンロード開始...")

            elif event == "--DOWNLOAD-PROGRESS--":
                d = values if isinstance(values, dict) else {}
                downloaded = float(d.get("downloaded_bytes", 0) or 0)
                total = d.get("total_bytes")
                if total is None:
                    total = d.get("total_bytes_estimate")
                try:
                    total = float(total or 0)
                except Exception:
                    total = 0.0
                if total > 0:
                    pct = (downloaded / total) * 100.0
                    window["status"].update(f"ダウンロード中... {pct:.1f}%")
                else:
                    window["status"].update("ダウンロード中...")

            elif event == "--DOWNLOAD-COMPLETE--":
                window["status"].update("ダウンロード完了!")

            elif event == "--DOWNLOAD-ERROR--":
                window["status"].update(f"ダウンロードエラー: {values.get('error', '')}")

            # ------------- 生配信 -------------
            elif event == "生配信情報取得":
                url = (values.get("live_url") or "").strip()
                if not url:
                    window["live_status"].update("URLを入力してください")
                    continue
                window["live_status"].update("生配信情報取得中...")
                run_in_thread(worker_fetch_live_info, manager, url, window)

            elif event == "生配信ダウンロード開始":
                url = (values.get("live_url") or "").strip()
                if not url:
                    window["live_status"].update("URLを入力してください")
                    continue

                selected_format = values.get("live_formats") or ""
                if not selected_format:
                    window["live_status"].update("フォーマットを選択してください")
                    continue

                save_path = values.get("live_save_path") or ""
                if not save_path:
                    window["live_status"].update("保存先を選択してください")
                    continue

                format_id = parse_selected_format_id(selected_format)
                live_from_start = bool(values.get("live_from_start", True))

                if live_from_start:
                    window["live_status"].update("配信開始からダウンロード中...")
                else:
                    window["live_status"].update("現在位置からダウンロード中...")


                run_in_thread(

                    worker_download_single,

                    manager,

                    url,

                    format_id,

                    save_path,

                    window,

                    mode,
                    True,

                    live_from_start,

                )


            elif event == "live_stop":
                manager.stop()
                window["live_status"].update("生配信ダウンロードを停止しました")

            elif event == "--LIVE-INFO-READY--":
                window["live_title"].update(values.get("title", ""))
                window["live_formats"].update(values=values.get("formats", []))
                window["live_status"].update("生配信情報取得完了")
                title = values.get("title")

                if title:
                    tmpl = settings.get("filename_template", "%(title)s.%(ext)s")
                    suggested = str(get_default_download_folder() / tmpl)
                    window["live_save_path"].update(suggested)


            elif event == "--LIVE-INFO-ERROR--":
                window["live_title"].update("エラー")
                window["live_status"].update(f"生配信情報取得エラー: {values.get('error', '')}")

            elif event == "--LIVE-DOWNLOAD-START--":
                window["live_status"].update("生配信ダウンロード開始...")

            elif event == "--LIVE-DOWNLOAD-PROGRESS--":
                d = values if isinstance(values, dict) else {}
                downloaded = float(d.get("downloaded_bytes", 0) or 0)
                size_mb = downloaded / (1024 * 1024)
                window["live_status"].update(f"生配信ダウンロード中... {size_mb:.1f}MB")

            elif event == "--LIVE-DOWNLOAD-COMPLETE--":
                window["live_status"].update("生配信ダウンロード完了!")

            elif event == "--LIVE-DOWNLOAD-ERROR--":
                window["live_status"].update(f"生配信ダウンロードエラー: {values.get('error', '')}")

            # ------------- 連続ダウンロード（URL リスト / プレイリスト） -------------
            elif event == "連続ダウンロード開始":
                url_input = (values.get("url_input") or "").strip()
                if not url_input:
                    window["renzoku_status"].update("URLリストファイルまたはプレイリストURLを入力してください")
                    continue

                save_folder = values.get("renzoku_folder") or str(get_default_download_folder())
                format_type = "bestaudio" if values.get("renzoku_audio") else "bestvideo+bestaudio/best"

                if os.path.exists(url_input):
                    window["renzoku_status"].update("URLリスト読み込み中...")
                    run_in_thread(worker_download_url_list, manager, url_input, format_type, save_folder, mode, window)
                else:
                    window["renzoku_status"].update("ダウンロード開始...")
                    run_in_thread(worker_download_playlist, manager, url_input, format_type, save_folder, mode, window)

            elif event in ("連続ダウンロード停止", "renzoku_stop"):
                manager.stop()
                window["renzoku_status"].update("連続ダウンロードを停止しました")

            # UI イベントによる UI 更新（連続）
            elif event == "--RENZOKU-PROGRESS--":
                d = values if isinstance(values, dict) else {}
                downloaded = d.get("downloaded_bytes")
                total = d.get("total_bytes")
                filename = d.get("filename", "")
                try:
                    if downloaded is not None and total is not None:
                        downloaded_f = float(downloaded)
                        total_f = float(total)
                        if total_f > 0:
                            pct = (downloaded_f / total_f) * 100.0
                            if filename:
                                basename = os.path.basename(filename)
                                window["renzoku_status"].update(f"ダウンロード中: {basename} - {pct:.1f}%")
                            else:
                                window["renzoku_status"].update(f"ダウンロード中... {pct:.1f}%")
                        else:
                            window["renzoku_status"].update("ダウンロード中...")
                    else:
                        window["renzoku_status"].update("ダウンロード中...")
                except Exception:
                    window["renzoku_status"].update("ダウンロード中...")

            elif event == "--RENZOKU-DOWNLOAD-COMPLETE--":
                window["renzoku_status"].update("ダウンロード完了!")

            elif event == "--RENZOKU-DOWNLOAD-ERROR--":
                window["renzoku_status"].update(f"ダウンロードエラー: {values.get('error', '')}")

            elif event == "--URL-LIST-START--":
                total = values.get("total", 0)
                window["renzoku_status"].update(f"連続ダウンロード開始 ({total}件)")

            elif event == "--URL-LIST-PROGRESS--":
                cur = values.get("current")
                total = values.get("total")
                u = values.get("url", "")
                if cur is not None and total is not None:
                    window["renzoku_status"].update(f"ダウンロード中 ({cur}/{total}): {u[:50]}...")
                else:
                    window["renzoku_status"].update("ダウンロード中...")

            elif event == "--URL-LIST-COMPLETE--":
                total = values.get("total", 0)
                window["renzoku_status"].update(f"連続ダウンロード完了 ({total}件)")

            elif event == "--URL-LIST-ERROR--":
                cur = values.get("current")
                total = values.get("total")
                err = values.get("error", "")
                if cur is not None and total is not None:
                    window["renzoku_status"].update(f"エラー ({cur}/{total}): {err}")
                else:
                    window["renzoku_status"].update(f"エラー: {err}")

            elif event == "--URL-LIST-FILE-ERROR--":
                window["renzoku_status"].update(f"URLリスト読み込みエラー: {values.get('error', '')}")

            # ------------- 設定 -------------
            elif event == "説明書を開く":
                try:
                    webbrowser.open("https://github.com/taisan11/yt-dlp-gui")
                except Exception as e:
                    logger.exception("説明書を開けませんでした: %s", e)


if __name__ == "__main__":
    main()
