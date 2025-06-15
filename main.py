import yt_dlp
import TkEasyGUI as eg
import os
import threading
from pathlib import Path
import signal

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
        
        # Cookieファイルが設定されている場合は追加
        cookie_file = window.read()["cookie_list"]
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
            
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

def download_video(url, format_id, save_path, window, is_single_mode=True):
    """バックグラウンドで動画をダウンロードする関数"""
    try:
        window.post_event("--DOWNLOAD-START--", None)
        if is_single_mode:
            # 単一モード：指定されたファイルパスに保存
            ydl_opts = {
                'format': format_id,
                'outtmpl': save_path,
                'progress_hooks': [lambda d: window.post_event("--DOWNLOAD-PROGRESS--", d) if d['status'] == 'downloading' else None],
            }
        else:
            # 連続モード：フォルダ内にファイル名自動生成で保存
            ydl_opts = {
                'format': format_id,
                'outtmpl': f"{save_path}/%(title)s.%(ext)s",
                'progress_hooks': [lambda d: window.post_event("--DOWNLOAD-PROGRESS--", d) if d['status'] == 'downloading' else None],
            }
            
        # Cookieファイルが設定されている場合は追加
        cookie_file = window.read()["cookie_list"]
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        window.post_event("--DOWNLOAD-COMPLETE--", None)
    except Exception as e:
        window.post_event("--DOWNLOAD-ERROR--", {"error": str(e)})

def download_url_list(url_list_path, format_type, save_path, window):
    """URLリストファイルを非同期でダウンロードする関数"""
    try:
        with open(url_list_path, "r", encoding="utf-8") as f:
            urls = f.readlines()
        
        total_urls = len([url.strip() for url in urls if url.strip()])
        
        # イベントをメインスレッドに送信
        window.after(0, lambda: update_ui_start(window, total_urls))
        
        for i, url in enumerate(urls, 1):
            url = url.strip()
            if not url:
                continue
            
            # イベントをメインスレッドに送信
            window.after(0, lambda w=window, curr=i, tot=total_urls, u=url: 
                update_ui_progress(w, curr, tot, u))
            
            try:
                # 各URLを個別にダウンロード
                ydl_opts = {
                    'format': format_type,
                    'outtmpl': f"{save_path}/%(title)s.%(ext)s",
                    'quiet': True,
                }
                
                # Cookieファイルが設定されている場合は追加
                cookie_file = None
                try:
                    cookie_file = window.read()["cookie_list"]
                except:
                    pass
                    
                if cookie_file and os.path.exists(cookie_file):
                    ydl_opts['cookiefile'] = cookie_file
                    
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    
            except Exception as e:
                # エラーメッセージをメインスレッドに送信
                error_msg = str(e)
                window.after(0, lambda w=window, curr=i, tot=total_urls, err=error_msg: 
                    update_ui_error(w, curr, tot, err))
                continue
        
        # 完了メッセージをメインスレッドに送信
        window.after(0, lambda w=window, tot=total_urls: update_ui_complete(w, tot))
        
    except Exception as e:
        # ファイルエラーメッセージをメインスレッドに送信
        error_msg = str(e)
        window.after(0, lambda w=window, err=error_msg: update_ui_file_error(w, err))

# メインスレッドで実行される関数群（UI更新用）
def update_ui_start(window, total_urls):
    window.post_event("--URL-LIST-START--", {"total": total_urls})

def update_ui_progress(window, current, total, url):
    window.post_event("--URL-LIST-PROGRESS--", {"current": current, "total": total, "url": url[:50]})

def update_ui_error(window, current, total, error):
    window.post_event("--URL-LIST-ERROR--", {"current": current, "total": total, "error": error})

def update_ui_complete(window, total):
    window.post_event("--URL-LIST-COMPLETE--", {"total": total})

def update_ui_file_error(window, error):
    window.post_event("--URL-LIST-FILE-ERROR--", {"error": error})


def download_playlist_simple(url, format_type, save_path, window):
    """連続ダウンロード用のシンプルなプレイリストダウンロード関数"""
    try:
        ydl_opts = {
            'format': format_type,
            'outtmpl': f"{save_path}/%(playlist_index)s - %(title)s.%(ext)s" if "playlist" in url or "channel" in url else f"{save_path}/%(title)s.%(ext)s",
            'progress_hooks': [
                lambda d: window.after(0, lambda: renzoku_progress_hook(window, d)) 
                if d['status'] == 'downloading' else None
            ],
        }
        
        # Cookieファイルが設定されている場合は追加
        cookie_file = None
        try:
            cookie_file = window.read()["cookie_list"]
        except:
            pass
            
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        window.after(0, lambda: window.post_event("--RENZOKU-DOWNLOAD-COMPLETE--", None))
    except Exception as e:
        error_msg = str(e)
        window.after(0, lambda: window.post_event("--RENZOKU-DOWNLOAD-ERROR--", {"error": error_msg}))

# プログレスフックをメインスレッドで実行するヘルパー関数
def renzoku_progress_hook(window, d):
    window.post_event("--RENZOKU-PROGRESS--", d)

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
            eg.Tab("連続", layout_renzoku),
            eg.Tab("設定", layout_settings)
        ]]
    )],
]

# create a window
with eg.Window("ようつべだうろだ", layout,resizable=True) as window:
    # event loop
    for event, values in window.event_iter():
        if event == eg.WIN_CLOSED:
            break
        ####################
        ## 単一動画ダウンロード処理
        ####################
        elif event == "読み込み":
            url = values["url"]
            if url:
                window["status"].update("情報取得中...")
                threading.Thread(target=fetch_video_info, args=(url, window), daemon=True).start()
        elif event == "単一ダウンロード開始":
            url = values["url"]
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
            threading.Thread(target=download_video, args=(url, format_id, save_path, window, True), daemon=True).start()
        ####################
        ## 連続動画ダウンロード処理
        ####################
        elif event == "--RENZOKU-PROGRESS--":
            try:
                progress_data = values.get(event)
                if not progress_data and isinstance(values, dict):
                    progress_data = values
                    
                if progress_data and isinstance(progress_data, dict):
                    if 'downloaded_bytes' in progress_data and 'total_bytes' in progress_data:
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
                else:
                    window["renzoku_status"].update("ダウンロード中...")
            except Exception as e:
                window["renzoku_status"].update(f"ダウンロード中... (エラー: {str(e)})")
        elif event == "--RENZOKU-DOWNLOAD-COMPLETE--":
            window["renzoku_status"].update("ダウンロード完了!")
        elif event == "--RENZOKU-DOWNLOAD-ERROR--":
            window["renzoku_status"].update(f"ダウンロードエラー: {values['error']}")
        elif event == "連続ダウンロード開始":
            url_input = values["url_input"]
            
            if not url_input:
                window["renzoku_status"].update("URLリストファイルまたはプレイリストURLを入力してください")
                continue
                
            save_folder = values.get("renzoku_folder") or get_download_folder()
            format_type = "bestaudio" if values.get("renzoku_audio") else "bestvideo+bestaudio/best"
            
            # 入力がファイルパスかURLかを判定
            if os.path.exists(url_input):
                # ファイルパスの場合：URLリストファイルとして処理（非同期）
                window["renzoku_status"].update("URLリスト読み込み中...")
                threading.Thread(target=download_url_list, args=(url_input, format_type, save_folder, window), daemon=True).start()
            else:
                # URLの場合：プレイリストURLとして処理
                window["renzoku_status"].update("ダウンロード開始...")
                threading.Thread(target=download_playlist_simple, args=(url_input, format_type, save_folder, window), daemon=True).start()
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
        elif event == "--VIDEO-INFO-READY--":
            window["title"].update(values["title"])
            window["list"].update(values=values["formats"])
            window["status"].update("情報取得完了")
            # 保存先フィールドにタイトルを含めたファイル名を自動提案
            if values.get("title"):
                # 不正な文字を除去してファイル名として使用可能にする
                safe_title = "".join(c for c in values["title"] if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                download_folder = get_download_folder()
                suggested_path = f"{download_folder}/{safe_title}.%(ext)s"
                window["save_path"].update(suggested_path)
        elif event == "--VIDEO-INFO-ERROR--":
            window["title"].update("エラー")
            window["status"].update(f"情報取得エラー: {values}")
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
