from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MAX_URLS = 100
TIKTOK_DOMAINS = (
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
)
COOKIES_PATH = os.environ.get("TIKTOK_COOKIES_PATH")
DOWNLOAD_FORMAT = os.environ.get(
    "TIKTOK_VIDEO_FORMAT", "bv*+ba/bestvideo+bestaudio/best"
)

logger = logging.getLogger("tiktok_downloader")

app = FastAPI(title="TikTok Bulk Downloader")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class DownloadRequest(BaseModel):
    urls: List[str]

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls: List[str]) -> List[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for raw in urls:
            url = (raw or "").strip()
            if not url:
                continue
            normalized = cls._ensure_valid_url(url)
            if normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)

        if not cleaned:
            raise ValueError("TikTokのURLを1件以上入力してください。")
        if len(cleaned) > MAX_URLS:
            raise ValueError(f"URLは最大{MAX_URLS}件まで指定できます。")

        return cleaned

    @staticmethod
    def _ensure_valid_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URLスキームはhttpまたはhttpsのみ利用できます。")

        hostname = (parsed.hostname or "").lower()
        if not any(hostname == domain or hostname.endswith(f".{domain}") for domain in TIKTOK_DOMAINS):
            raise ValueError("TikTokのURLのみ指定してください。")

        return url


def _iter_file_chunks(file_path: Path, chunk_size: int = 1024 * 1024) -> Iterable[bytes]:
    with file_path.open("rb") as file:
        while True:
            data = file.read(chunk_size)
            if not data:
                break
            yield data


def _cleanup_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
        except Exception:
            # 失敗してもアプリの挙動には影響しないため握りつぶす
            continue


def _build_yt_dlp_options(output_template: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": output_template,
        "retries": 3,
        "format": DOWNLOAD_FORMAT,
        "merge_output_format": "mp4",
        "noprogress": True,
        "geo_bypass": True,
        "noplaylist": True,
        "ignore_no_formats_error": True,
    }

    if COOKIES_PATH:
        cookie_file = Path(COOKIES_PATH).expanduser()
        if cookie_file.exists():
            options["cookies"] = str(cookie_file)
        else:
            logger.warning(
                "TIKTOK_COOKIES_PATH=%s が見つかりませんでした。認証が必要な動画は失敗する可能性があります。",
                cookie_file,
            )

    return options


def _run_download_job(urls: List[str]) -> Tuple[Path, dict, Path]:
    job_id = uuid.uuid4().hex
    work_dir = Path(tempfile.mkdtemp(prefix="tiktok_dl_"))
    output_template = str(work_dir / "%(id)s_%(creator)s.%(ext)s")

    summary = {
        "job_id": job_id,
        "total": len(urls),
        "success": 0,
        "failed": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    ydl_opts = _build_yt_dlp_options(output_template)

    with YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            try:
                ydl.download([url])
                summary["success"] += 1
            except DownloadError as exc:
                summary["failed"].append({"url": url, "reason": str(exc)})
            except Exception as exc:  # noqa: BLE001
                summary["failed"].append({"url": url, "reason": str(exc)})

    downloaded_files = [path for path in work_dir.iterdir() if path.is_file()]
    if not downloaded_files:
        raise RuntimeError("動画のダウンロードに失敗しました。")

    report_path = work_dir / "download_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    zip_base = Path(tempfile.gettempdir()) / work_dir.name
    zip_file_path = Path(
        shutil.make_archive(str(zip_base), "zip", root_dir=work_dir)
    )

    return zip_file_path, summary, work_dir


@app.get("/", response_class=HTMLResponse)
def get_index() -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="フロントエンドファイルが見つかりません。")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/download")
async def download_videos(payload: DownloadRequest, background_tasks: BackgroundTasks) -> StreamingResponse:
    try:
        zip_path, summary, work_dir = await asyncio.to_thread(_run_download_job, payload.urls)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="予期しないエラーが発生しました。") from exc

    background_tasks.add_task(_cleanup_paths, [zip_path, work_dir])

    headers = {
        "Content-Disposition": f'attachment; filename="tiktok_videos_{summary["job_id"]}.zip"',
        "X-Job-Id": summary["job_id"],
        "X-Download-Summary": json.dumps(
            {
                "total": summary["total"],
                "success": summary["success"],
                "failed": len(summary["failed"]),
            }
        ),
    }

    return StreamingResponse(
        _iter_file_chunks(zip_path),
        media_type="application/zip",
        headers=headers,
    )

