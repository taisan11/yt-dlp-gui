import yt_dlp
import TkEasyGUI as eg
import os
import threading
from pathlib import Path

# グローバル変数でダウンロードプロセスを追跡
current_download_process = None

def stop_download():
    global current_download_process
    if current_download_process:
        try:
            if hasattr(current_download_process, 'params'):
                current_download_process.params['abort'] = True
            current_download_process = None
            return True
        except Exception:
            current_download_process = None
            return False
    return False

def get_download_folder():
    home = Path.home()
    if os.name == 'nt':
        download = home / 'Downloads'
    else:
        download = home / 'Downloads'
    return download

def fetch_video_info(url, cookie_file, window):
    try:
        window.post_event("--VIDEO-INFO-START--", None)
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'outtmpl': '%(title)s.%(ext)s',
        }
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if info_dict:
                title = info_dict.get('title', None)
                is_live = info_dict.get('is_live', False)
                formats = []
                for f in info_dict['formats']:
                    format_str = f"{f['format_id']} - "
                    if 'resolution' in f and f['resolution']:
                        format_str += f"{f['resolution']} "
                    if 'ext' in f:
                        format_str += f"({f['ext']}) "
                    if 'filesize' in f and f['filesize']:
                        size_mb = f['filesize'] / (1024 * 1024)
                        format_str += f"{size_mb:.1f}MB "
                    formats.append(format_str.strip())
                if is_live:
                    window.post_event("--VIDEO-INFO-LIVE--", {"title": title, "url": url})
                else:
                    window.post_event("--VIDEO-INFO-READY--", {"title": title, "formats": formats})
            else:
                window.post_event("--VIDEO-INFO-ERROR--", {"error": "Invalid URL or video not found"})
    except Exception as e:
        window.post_event("--VIDEO-INFO-ERROR--", {"error": str(e)})

def fetch_live_info(url, cookie_file, window):
    try:
        window.post_event("--LIVE-INFO-START--", None)
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'outtmpl': '%(title)s.%(ext)s',
        }
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if info_dict:
                title = info_dict.get('title', None)
                is_live = info_dict.get('is_live', False)
                formats = []
                for f in info_dict['formats']:
                    format_str = f"{f['format_id']} - "
                    if 'resolution' in f and f['resolution']:
                        format_str += f"{f['resolution']} "
                    if 'ext' in f:
                        format_str += f"({f['ext']}) "
                    if 'filesize' in f and f['filesize']:
                        size_mb = f['filesize'] / (1024 * 1024)
                        format_str += f"{size_mb:.1f}MB "
                    formats.append(format_str.strip())
                if is_live:
                    window.post_event("--LIVE-INFO-READY--", {"title": title, "formats": formats})
                else:
                    window.post_event("--LIVE-INFO-ERROR--", {"error": "この URL は生配信ではありません"})
            else:
                window.post_event("--LIVE-INFO-ERROR--", {"error": "Invalid URL or video not found"})
    except Exception as e:
        window.post_event("--LIVE-INFO-ERROR--", {"error": str(e)})

def download_video(url, format_id, save_path, cookie_file, window, is_single_mode=True, is_livestream=False, live_from_start=True):
    try:
        window.post_event("--DOWNLOAD-START--", None)
        ydl_opts = {
            'format': format_id,
            'progress_hooks': [lambda d: window.post_event("--DOWNLOAD-PROGRESS--", d) if d['status'] == 'downloading' else None],
        }
        if is_livestream:
            ydl_opts.update({
                'live_from_start': live_from_start,
                'wait_for_video': (5, 10),
                'concurrent_fragment_downloads': 5,
                'retries': 10,
            })
        if is_single_mode:
            ydl_opts['outtmpl'] = save_path
        else:
            ydl_opts['outtmpl'] = f"{save_path}/%(title)s.%(ext)s"
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
        global current_download_process
        current_download_process = yt_dlp.YoutubeDL(ydl_opts)
        current_download_process.download([url])
        current_download_process = None
        window.post_event("--DOWNLOAD-COMPLETE--", None)
    except Exception as e:
        current_download_process = None
        window.post_event("--DOWNLOAD-ERROR--", {"error": str(e)})

def download_livestream(url, format_id, save_path, cookie_file, window, live_from_start=True):
    try:
        window.post_event("--LIVE-DOWNLOAD-START--", None)
        ydl_opts = {
            'format': format_id,
            'progress_hooks': [lambda d: window.post_event("--LIVE-DOWNLOAD-PROGRESS--", d) if d['status'] == 'downloading' else None],
            'live_from_start': live_from_start,
            'wait_for_video': (5, 10),
            'concurrent_fragment_downloads': 5,
            'retries': 10,
        }
        ydl_opts['outtmpl'] = save_path
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
        global current_download_process
        current_download_process = yt_dlp.YoutubeDL(ydl_opts)
        current_download_process.download([url])
        current_download_process = None
        window.post_event("--LIVE-DOWNLOAD-COMPLETE--", None)
    except Exception as e:
        current_download_process = None
        window.post_event("--LIVE-DOWNLOAD-ERROR--", {"error": str(e)})

def download_url_list(url_list_path, format_type, save_path, cookie_file, window):
    try:
        with open(url_list_path, "r", encoding="utf-8") as f:
            urls = f.readlines()
        total_urls = len([url.strip() for url in urls if url.strip()])
        window.post_event("--URL-LIST-START--", {"total": total_urls})
        for i, url in enumerate(urls, 1):
            url = url.strip()
            if not url:
                continue
            window.post_event("--URL-LIST-PROGRESS--", {"current": i, "total": total_urls, "url": url[:50]})
            try:
                ydl_opts = {
                    'format': format_type,
                    'outtmpl': f"{save_path}/%(title)s.%(ext)s",
                    'quiet': True,
                }
                if cookie_file and os.path.exists(cookie_file):
                    ydl_opts['cookiefile'] = cookie_file
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                error_msg = str(e)
                window.post_event("--URL-LIST-ERROR--", {"current": i, "total": total_urls, "error": error_msg})
                continue
        window.post_event("--URL-LIST-COMPLETE--", {"total": total_urls})
    except Exception as e:
        error_msg = str(e)
        window.post_event("--URL-LIST-FILE-ERROR--", {"error": error_msg})

def download_playlist_simple(url, format_type, save_path, cookie_file, window):
    try:
        ydl_opts = {
            'format': format_type,
            'outtmpl': f"{save_path}/%(playlist_index)s - %(title)s.%(ext)s" if "playlist" in url or "channel" in url else f"{save_path}/%(title)s.%(ext)s",
            'progress_hooks': [lambda d: window.post_event("--RENZOKU-PROGRESS--", d) if d['status'] == 'downloading' else None],
        }
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        window.post_event("--RENZOKU-DOWNLOAD-COMPLETE--", None)
    except Exception as e:
        error_msg = str(e)
        window.post_event("--RENZOKU-DOWNLOAD-ERROR--", {"error": error_msg})

# 生配信用のレイアウト
layout_live = [
    [eg.Text("生配信ダウンロード!!",font=("Helvetica", 13,"bold"))],
    [eg.Text("生配信URL:"),eg.InputText("", key="live_url"), eg.Button("生配信情報取得")],
    [eg.Combo(values=[], key="live_formats", size=(40, 10,"bold"))],
    [eg.Text("ダウンロードオプション:")],
    [eg.Radio("配信開始からダウンロード", "live_option", key="live_from_start", default=True)],
    [eg.Radio("現在の位置からダウンロード", "live_option", key="live_from_now")],
    [eg.Text("保存先:"),eg.InputText(key="live_save_path"),eg.FileSaveAs("ファイル保存先")],
    [eg.Button("生配信ダウンロード開始"), eg.Button("生配信ダウンロード停止", key="live_stop")],
    [eg.Text("情報")],
    [eg.Text("", key="live_title")],
    [eg.Text("", key="live_status")]
]

layout_renzoku = [
    [eg.Text("連続ダウンロード!!",font=("Helvetica", 13,"bold"))],
    [eg.Text("URLリストファイルまたはプレイリストURL:"),eg.InputText("", key="url_input"),eg.FileBrowse("URLリスト")],
    [eg.Text("出力形式:"),eg.Radio("video","AV",default=True,key="renzoku_video"), eg.Radio("audio","AV",key="renzoku_audio")],
    [eg.Text("保存フォルダ:"),eg.InputText(key="renzoku_folder"),eg.FolderBrowse("フォルダ選択")],
    [eg.Button("連続ダウンロード開始")],
    [eg.Text("", key="renzoku_status")],
]

layout_main = [
    [eg.Text("動画とかダウンローダー",font=("Helvetica", 20))],
    [eg.Text("単一動画ダウンロード!!",font=("Helvetica", 13,"bold"))],
    [eg.Text("URL:"),eg.InputText("", key="url"), eg.Button("読み込み")],
    [eg.Combo(values=[], key="list", size=(40, 10,"bold"))],
    [eg.Text("保存設定",font=("Helvetica", 13,"bold"))],
    [eg.Text("保存先:"),eg.InputText(key="save_path"),eg.FileSaveAs("ファイル保存先")],
    [eg.Button("単一ダウンロード開始")],
    [eg.Text("情報")],
    [eg.Text("", key="title")],
    [eg.Text("", key="status")]
]

layout_settings = [
    [eg.Text("設定", font=("Helvetica", 20))],
    [eg.Text("CookieList:"), eg.InputText("", key="cookie_list"), eg.FileBrowse("選択")],
]

layout = [
    [eg.TabGroup(
        [[
            eg.Tab("一般", layout_main),
            eg.Tab("生配信", layout_live),
            eg.Tab("連続", layout_renzoku),
            eg.Tab("設定", layout_settings)
        ]]
    )],
]

# create a window
with eg.Window("ようつべだうろだ", layout, resizable=True) as window:
    # event loop
    for event, values in window.event_iter():
        if event == eg.WIN_CLOSED:
            break
        ####################
        ## 単一動画ダウンロード処理
        ####################
        elif event == "読み込み":
            url = values["url"]
            cookie_file = values.get("cookie_list")
            if url:
                window["status"].update("情報取得中...")
                threading.Thread(target=fetch_video_info, args=(url, cookie_file, window), daemon=True).start()
        elif event == "単一ダウンロード開始":
            url = values["url"]
            cookie_file = values.get("cookie_list")
            if not url:
                window["status"].update("URLを入力してください")
                continue
                
            selected_format = values["list"]
            if not selected_format:
                window["status"].update("フォーマットを選択してください")
                continue
                
            # ファイル保存先の確認
            save_path = values.get("save_path")
            if not save_path:
                window["status"].update("保存先を選択してください")
                continue
                
            format_id = selected_format.split(" - ")[0]
            window["status"].update("ダウンロード開始...")
                
            threading.Thread(
                target=download_video, 
                args=(url, format_id, save_path, cookie_file, window, True, False, True), 
                daemon=True
            ).start()
        ####################
        ## 生配信ダウンロード処理
        ####################
        elif event == "生配信情報取得":
            url = values["live_url"]
            cookie_file = values.get("cookie_list")
            if url:
                window["live_status"].update("生配信情報取得中...")
                threading.Thread(target=fetch_live_info, args=(url, cookie_file, window), daemon=True).start()
        elif event == "生配信ダウンロード開始":
            url = values["live_url"]
            cookie_file = values.get("cookie_list")
            if not url:
                window["live_status"].update("URLを入力してください")
                continue
                
            selected_format = values["live_formats"]
            if not selected_format:
                window["live_status"].update("フォーマットを選択してください")
                continue
                
            # ファイル保存先の確認
            save_path = values.get("live_save_path")
            if not save_path:
                window["live_status"].update("保存先を選択してください")
                continue
                
            format_id = selected_format.split(" - ")[0]
            live_from_start = values.get("live_from_start", True)
            
            if live_from_start:
                window["live_status"].update("配信開始からダウンロード中...")
            else:
                window["live_status"].update("現在位置からダウンロード中...")
                
            threading.Thread(
                target=download_livestream, 
                args=(url, format_id, save_path, cookie_file, window, live_from_start), 
                daemon=True
            ).start()
        elif event == "live_stop":
            if stop_download():
                window["live_status"].update("生配信ダウンロードを停止しました")
            else:
                window["live_status"].update("停止するダウンロードがないか、停止処理に失敗しました")
        elif event == "連続ダウンロード開始":
            url_input = values["url_input"]
            cookie_file = values.get("cookie_list")
            if not url_input:
                window["renoku_status"].update("URLリストファイルまたはプレイリストURLを入力してください")
                continue
                
            save_folder = values.get("renzoku_folder") or get_download_folder()
            format_type = "bestaudio" if values.get("renzoku_audio") else "bestvideo+bestaudio/best"
            
            # 入力がファイルパスかURLかを判定
            if os.path.exists(url_input):
                # ファイルパスの場合：URLリストファイルとして処理（非同期）
                window["renzoku_status"].update("URLリスト読み込み中...")
                threading.Thread(target=download_url_list, args=(url_input, format_type, save_folder, cookie_file, window), daemon=True).start()
            else:
                # URLの場合：プレイリストURLとして処理
                window["renzoku_status"].update("ダウンロード開始...")
                threading.Thread(target=download_playlist_simple, args=(url_input, format_type, save_folder, cookie_file, window), daemon=True).start()
        # --- イベントによるUI更新 ---
        elif event == "--VIDEO-INFO-READY--":
            window["title"].update(values["title"])
            window["list"].update(values=values["formats"])
            window["status"].update("情報取得完了")
            if values.get("title"):
                safe_title = "".join(c for c in values["title"] if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                download_folder = get_download_folder()
                suggested_path = f"{download_folder}/{safe_title}.%(ext)s"
                window["save_path"].update(suggested_path)
        elif event == "--VIDEO-INFO-LIVE--":
            window["title"].update(values["title"])
            window["status"].update("この URL は生配信です。生配信タブで処理してください。")
            window["live_url"].update(values["url"])
        elif event == "--VIDEO-INFO-ERROR--":
            window["title"].update("エラー")
            window["status"].update(f"情報取得エラー: {values['error']}")
        elif event == "--DOWNLOAD-START--":
            window["status"].update("ダウンロード開始...")
        elif event == "--DOWNLOAD-PROGRESS--":
            progress_data = values if isinstance(values, dict) else None
            if progress_data and 'downloaded_bytes' in progress_data and 'total_bytes' in progress_data:
                try:
                    downloaded = float(progress_data['downloaded_bytes'])
                    total = float(progress_data['total_bytes'])
                    if total > 0:
                        percentage = (downloaded / total) * 100
                        window["status"].update(f"ダウンロード中... {percentage:.1f}%")
                    else:
                        window["status"].update("ダウンロード中...")
                except (TypeError, ValueError) as e:
                    window["status"].update(f"ダウンロード中... (進捗計算エラー: {e})")
            elif progress_data and 'downloaded_bytes' in progress_data and 'total_bytes_estimate' in progress_data:
                try:
                    downloaded = float(progress_data['downloaded_bytes'])
                    total = float(progress_data['total_bytes_estimate'])
                    if total > 0:
                        percentage = (downloaded / total) * 100
                        window["status"].update(f"ダウンロード中... {percentage:.1f}% (推定)")
                    else:
                        window["status"].update("ダウンロード中...")
                except (TypeError, ValueError):
                    window["status"].update("ダウンロード中... (進捗不明)")
            else:
                window["status"].update("ダウンロード中...")
        elif event == "--DOWNLOAD-COMPLETE--":
            window["status"].update("ダウンロード完了!")
        elif event == "--DOWNLOAD-ERROR--":
            window["status"].update(f"ダウンロードエラー: {values['error']}")
        elif event == "--LIVE-INFO-READY--":
            window["live_title"].update(values["title"])
            window["live_formats"].update(values=values["formats"])
            window["live_status"].update("生配信情報取得完了")
            if values.get("title"):
                safe_title = "".join(c for c in values["title"] if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                download_folder = get_download_folder()
                suggested_path = f"{download_folder}/{safe_title}.%(ext)s"
                window["live_save_path"].update(suggested_path)
        elif event == "--LIVE-INFO-ERROR--":
            window["live_title"].update("エラー")
            window["live_status"].update(f"生配信情報取得エラー: {values['error']}")
        elif event == "--LIVE-DOWNLOAD-START--":
            window["live_status"].update("生配信ダウンロード開始...")
        elif event == "--LIVE-DOWNLOAD-PROGRESS--":
            progress_data = values if isinstance(values, dict) else None
            if progress_data and 'downloaded_bytes' in progress_data:
                downloaded = float(progress_data['downloaded_bytes'])
                size_mb = downloaded / (1024 * 1024)
                window["live_status"].update(f"生配信ダウンロード中... {size_mb:.1f}MB")
            else:
                window["live_status"].update("生配信ダウンロード中...")
        elif event == "--LIVE-DOWNLOAD-COMPLETE--":
            window["live_status"].update("生配信ダウンロード完了!")
        elif event == "--LIVE-DOWNLOAD-ERROR--":
            window["live_status"].update(f"生配信ダウンロードエラー: {values['error']}")
        elif event == "--RENZOKU-PROGRESS--":
            progress_data = values if isinstance(values, dict) else None
            if progress_data and 'downloaded_bytes' in progress_data and 'total_bytes' in progress_data:
                try:
                    downloaded = float(progress_data['downloaded_bytes'])
                    total = float(progress_data['total_bytes'])
                    if total > 0:
                        percentage = (downloaded / total) * 100
                        filename = progress_data.get('filename', '')
                        if filename:
                            basename = os.path.basename(filename)
                            window["renzoku_status"].update(f"ダウンロード中: {basename} - {percentage:.1f}%")
                        else:
                            window["renzoku_status"].update(f"ダウンロード中... {percentage:.1f}%")
                    else:
                        window["renzoku_status"].update("ダウンロード中...")
                except (TypeError, ValueError):
                    window["renzoku_status"].update("ダウンロード中...")
            else:
                window["renzoku_status"].update("ダウンロード中...")
        elif event == "--RENZOKU-DOWNLOAD-COMPLETE--":
            window["renzoku_status"].update("ダウンロード完了!")
        elif event == "--RENZOKU-DOWNLOAD-ERROR--":
            window["renzoku_status"].update(f"ダウンロードエラー: {values['error']}")
        elif event == "--URL-LIST-START--":
            window["renzoku_status"].update(f"連続ダウンロード開始 ({values['total']}件)")
        elif event == "--URL-LIST-PROGRESS--":
            window["renzoku_status"].update(f"ダウンロード中 ({values['current']}/{values['total']}): {values['url']}...")
        elif event == "--URL-LIST-ERROR--":
            window["renzoku_status"].update(f"エラー ({values['current']}/{values['total']}): {values['error']}")
        elif event == "--URL-LIST-COMPLETE--":
            window["renzoku_status"].update(f"連続ダウンロード完了 ({values['total']}件)")
        elif event == "--URL-LIST-FILE-ERROR--":
            window["renzoku_status"].update(f"URLリスト読み込みエラー: {values['error']}")
