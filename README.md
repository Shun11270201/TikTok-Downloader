# TikTok Bulk Downloader

WebブラウザからTikTok動画のURL（最大100件）をまとめて入力して、mp4とレポートをZIPで取得できるFastAPIアプリです。ご自身のアカウントにアップロード済みの動画を安全にアーカイブする用途を想定しています。

## 機能概要

- URL貼り付けまたはテキスト/CSVファイルの読み込みで最大100件のTikTok URLを投入
- `yt-dlp` を利用してサーバー側で順次ダウンロード（mp4）
- 完了後に動画と `download_report.json` を含むZIPをブラウザへ返却
- 成功/失敗件数をレスポンスヘッダー経由でUIに表示

## 動作要件

- macOS / Linux / Windows
- Python 3.11 以上
- `ffmpeg`（高画質取得のため推奨、`yt-dlp` が自動検出）

## セットアップ

```bash
cd /Users/shuntadaki/Downloads/tiktok-downloader
python3 -m venv .venv
source .venv/bin/activate  # Windowsの場合は .venv\\Scripts\\activate
pip install -r requirements.txt
```

## アプリの起動

```bash
uvicorn main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開き、URLを入力して「一括ダウンロード」を押すとZIPがダウンロードされます。

## 認証が必要な投稿のダウンロード

「ログインが必要」「年齢制限」などが掛かっている動画は、ブラウザのクッキーを `yt-dlp` に渡す必要があります。

1. `yt-dlp --cookies-from-browser chrome --write-cookie-file ~/.config/tiktok_cookies.txt "https://www.tiktok.com/@you"` などでクッキーファイルを作成します。
2. 環境変数 `TIKTOK_COOKIES_PATH` でファイルパスを指定してアプリを起動します。

```bash
export TIKTOK_COOKIES_PATH=~/.config/tiktok_cookies.txt
uvicorn main:app --reload --port 8000
```

環境変数は `TIKTOK_VIDEO_FORMAT` でも上書き可能で、`yt-dlp` の `--format` と同じ指定が使えます（デフォルトは `bv*+ba/bestvideo+bestaudio/best`）。

## 注意事項

- TikTokの利用規約・著作権を遵守し、権利のある動画のみをダウンロードしてください。
- ダウンロードに失敗したURLは `download_report.json` の `failed` セクションとUI上のステータスで確認できます。
- ダウンロード結果はサーバー側の一時ディレクトリに保存され、レスポンス送信後に自動で削除されます。

