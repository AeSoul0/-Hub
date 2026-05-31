from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os

router = APIRouter(
    prefix="/api/media",
    tags=["media"]
)

class MediaRequest(BaseModel):
    query: str

@router.post("/download")
def download_media(req: MediaRequest):
    # Validate the incoming payload to ensure the search query is provided
    if not req.query:
        raise HTTPException(status_code=400, detail="Please provide an Artist and Title")
    
    # Create a temporary directory on the server to process the file before dispatching it
    os.makedirs("temp_downloads", exist_ok=True)
    
    # Configuration dictionary for the yt-dlp extraction engine
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'temp_downloads/%(title)s.%(ext)s',
        
        # Pointing to the precise local installation path for FFmpeg executable binaries
        'ffmpeg_location': 'C:/Users/samue/AppData/Local/Microsoft/WinGet/Links',
        
        'postprocessors': [
            {
                # Extract raw audio and encode it into a high-quality 320kbps MP3 format
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            },
            {
                # Embed fetched media metadata directly into the exported audio file
                'key': 'FFmpegMetadata',
            }
        ],
        # Fetch the top relevant result directly via YouTube's internal search parameter
        'default_search': 'ytsearch1',
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Execute the network search query and initialize the download stream
            info_dict = ydl.extract_info(req.query, download=True)
            info = info_dict['entries'][0] if 'entries' in info_dict else info_dict
                
            # Compute the final absolute file path for the encoded .mp3 artifact
            raw_filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(raw_filename)
            mp3_filename = base + ".mp3"
            
            # Verify successful conversion and existence of the final payload
            if not os.path.exists(mp3_filename):
                raise HTTPException(status_code=500, detail="MP3 conversion pipeline failed")
                
            filename_only = os.path.basename(mp3_filename)
            
            # Dispatch the file payload forcing an 'attachment' header response.
            # This explicitly instructs the client browser to prompt a local download save operation.
            return FileResponse(
                path=mp3_filename,
                media_type="audio/mpeg",
                filename=filename_only,
                headers={"Content-Disposition": f'attachment; filename="{filename_only}"'}
            )
    except Exception as e:
        # Catch and forward any unhandled stream/processing exceptions to the client
        raise HTTPException(status_code=500, detail=str(e))