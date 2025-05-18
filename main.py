import yt_dlp
import TkEasyGUI as eg
import os
import threading
from pathlib import Path

def get_download_folder():
    home = Path.home()
    if os.name == 'nt':  # Windows
        download = home / 'Downloads'
    else:  # macOSやLinux
        download = home / 'Downloads'
    return download

def fetch_video_info(url, window):
    """バックグラウンドで動画情報を取得する関数"""
    try:
        window["title"].update("読み込み中...")
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'outtmpl': '%(title)s.%(ext)s',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if info_dict:
                title = info_dict.get('title', None)
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
                window.post_event("--VIDEO-INFO-READY--", {"title": title, "formats": formats})
            else:
                window.post_event("--VIDEO-INFO-ERROR--", "Invalid URL or video not found")
    except Exception as e:
        window.post_event("--VIDEO-INFO-ERROR--", str(e))

def download_video(url, format_id, save_path, window):
    """バックグラウンドで動画をダウンロードする関数"""
    try:
        window.post_event("--DOWNLOAD-START--", None)
        ydl_opts = {
            'format': format_id,
            'outtmpl': f"{save_path}/%(title)s.%(ext)s",
            'progress_hooks': [lambda d: window.post_event("--DOWNLOAD-PROGRESS--", d) if d['status'] == 'downloading' else None],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        window.post_event("--DOWNLOAD-COMPLETE--", None)
    except Exception as e:
        window.post_event("--DOWNLOAD-ERROR--", {"error": str(e)})

def download_video_list(url, format_id, save_path, window):
    """バックグラウンドで動画情報を取得しダウンロードする関数"""
    try:
        window.post_event("--DOWNLOAD-START--", None)
        ydl_opts = {
            'format': format_type,
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if info_dict:
                # Get the best format ID based on selection
                format_id = info_dict.get('format_id')
                download_video(url, format_id, save_path, window)
        window.post_event("--DOWNLOAD-COMPLETE--", None)
    except Exception as e:
        window.post_event("--DOWNLOAD-ERROR--", {"error": str(e)})

test_layout = [
    [eg.Text("動画とかダウンローダー")],]

layout = [
    [eg.Text("動画とかダウンローダー",font=("Helvetica", 20))],
    [eg.Text("普通にダウンロード!!",font=("Helvetica", 13))],
    [eg.Text("URL:"),eg.InputText("", key="url"), eg.Button("読み込み")],
    [eg.Combo(values=[], key="list", size=(40, 10))],
    [eg.Text("連続ダウンロード!!",font=("Helvetica", 13))],
    [eg.InputText("", key="urllist"),eg.FileBrowse("URLリスト")],
    [eg.Radio("video","AV",default=True), eg.Radio("audio","AV")],
    [eg.InputText(key="folder"),eg.FolderBrowse("保存先"), eg.Button("保存")],
    [eg.Text("情報!!")],
    [eg.Text("", key="title")],
    [eg.Text("", key="status")]
]

# create a window
with eg.Window("Hello App", layout) as window:
    # event loop
    for event, values in window.event_iter():
        if event == eg.WIN_CLOSED:
            break
        elif event == "読み込み":
            url = values["url"]
            if url:
                window["status"].update("情報取得中...")
                threading.Thread(target=fetch_video_info, args=(url, window), daemon=True).start()
        elif event == "保存":
            url = values["url"]
            URLlist = values["urllist"]
            if URLlist:
                with open(URLlist, "r") as f:
                    urls = f.readlines()
                for url in urls:
                    url = url.strip()
                    if not url:
                        continue
                    save_path = values.get("folder") or get_download_folder()
                    # Determine format based on radio button selection
                    format_type = "bestaudio" if values["audio"] else "bestvideo+bestaudio/best"
                    window["status"].update(f"URLリストからダウンロード中: {url}...")
                    threading.Thread(target=download_video_list, args=(url, format_type, save_path, window), daemon=True).start()
            if not url:
                window["status"].update("URLを入力してください")
                continue
                
            selected_format = values["list"]
            if not selected_format:
                window["status"].update("フォーマットを選択してください")
                continue
                
            format_id = selected_format.split(" - ")[0]
            save_path = values.get("folder") or get_download_folder()
            
            window["status"].update("ダウンロード開始...")
            threading.Thread(target=download_video, args=(url, format_id, save_path, window), daemon=True).start()
        elif event == "--VIDEO-INFO-READY--":
            window["title"].update(values["title"])
            window["list"].update(values=values["formats"])
            window["status"].update("情報取得完了")
        elif event == "--VIDEO-INFO-ERROR--":
            window["title"].update("エラー")
            window["status"].update(f"情報取得エラー: {values['error']}")
        elif event == "--DOWNLOAD-START--":
            window["status"].update("ダウンロード開始...")
        elif event == "--DOWNLOAD-PROGRESS--":
            try:
                # イベントデータを適切に取得
                progress_data = values.get(event)
                if not progress_data and isinstance(values, dict):
                    # 直接valuesがデータである可能性を確認
                    progress_data = values
                    
                # データ構造を検証
                if progress_data and isinstance(progress_data, dict):
                    if 'downloaded_bytes' in progress_data and 'total_bytes' in progress_data:
                        try:
                            # 念のため型変換してエラーを防止
                            downloaded = float(progress_data['downloaded_bytes'])
                            total = float(progress_data['total_bytes'])
                            if total > 0:  # ゼロ除算を防止
                                percentage = (downloaded / total) * 100
                                window["status"].update(f"ダウンロード中... {percentage:.1f}%")
                            else:
                                window["status"].update("ダウンロード中...")
                        except (TypeError, ValueError) as e:
                            window["status"].update(f"ダウンロード中... (進捗計算エラー: {e})")
                    elif 'downloaded_bytes' in progress_data and 'total_bytes_estimate' in progress_data:
                        # 代替方法で計算
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
                        # bytes情報がない場合
                        window["status"].update("ダウンロード中...")
                else:
                    window["status"].update("ダウンロード中...")
            except Exception as e:
                # 何らかの予期せぬエラーが発生した場合
                window["status"].update(f"ダウンロード中... (エラー: {str(e)})")
        elif event == "--DOWNLOAD-COMPLETE--":
            window["status"].update("ダウンロード完了!")
        elif event == "--DOWNLOAD-ERROR--":
            window["status"].update(f"ダウンロードエラー: {values['error']}")