import os

import yt_dlp
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/media", tags=["media"])


class MediaRequest(BaseModel):
    query: str


@router.post("/download")
def download_media(req: MediaRequest, background_tasks: BackgroundTasks):
    """
    Processes the incoming search query, extracts the best audio stream via yt_dlp,
    converts it to a high-quality MP3 archive using the system's global FFmpeg installation,
    and returns it as a downloadable file. A background task ensures immediate disk cleanup.
    """
    if not req.query:
        raise HTTPException(status_code=400, detail="Please provide an Artist and Title")

    # Create an isolated runtime directory for processing temporary downloads
    os.makedirs("temp_downloads", exist_ok=True)

    # Configuration suite for the yt-dlp extraction engine
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "temp_downloads/%(title)s.%(ext)s",
        # NOTE: Explicit 'ffmpeg_location' removed to enforce cross-platform compatibility.
        # The engine will automatically locate the FFmpeg binary within the operating system's PATH.
        "postprocessors": [
            {
                # Extract raw audio streams and transcode them into a 320kbps MP3 artifact
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {
                # Embed fetched metadata tags directly into the generated MP3 file
                "key": "FFmpegMetadata",
            },
        ],
        "default_search": "ytsearch1",
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Execute search query and initiate down-streaming pipeline
            info_dict = ydl.extract_info(req.query, download=True)
            info = info_dict["entries"][0] if "entries" in info_dict else info_dict

            # Derive absolute path trajectories for the converted MP3 asset
            raw_filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(raw_filename)
            mp3_filename = base + ".mp3"

            # Validate output compilation integrity
            if not os.path.exists(mp3_filename):
                raise HTTPException(status_code=500, detail="MP3 conversion pipeline failed")

            filename_only = os.path.basename(mp3_filename)

            # RESOURCE PROTECTION: Register an asynchronous background task to purge
            # the local binary file from the disk storage pool immediately after the client transmission ends.
            background_tasks.add_task(os.remove, mp3_filename)

            return FileResponse(
                path=mp3_filename,
                media_type="audio/mpeg",
                filename=filename_only,
                headers={"Content-Disposition": f'attachment; filename="{filename_only}"'},
            )
    except Exception as e:
        # Intercept pipeline failures and forward structural errors cleanly to the client interface
        raise HTTPException(status_code=500, detail=str(e)) from e
