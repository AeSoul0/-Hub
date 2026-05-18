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
    if not req.query:
        raise HTTPException(status_code=400, detail="Inserisci Artista e Titolo")
    
    # Cartella temporanea sul server per elaborare il file prima di spedirlo
    os.makedirs("temp_downloads", exist_ok=True)
    
    ydl_opts = {
        'format': 'bestaudio/best', # Cattura la traccia audio sorgente con la qualità più alta possibile
        'outtmpl': 'temp_downloads/%(title)s.%(ext)s',
        'postprocessors': [
            {
                # Converte rigorosamente in MP3
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320', # Qualità massima assoluta per il formato MP3
            },
            {
                # Aggiunge i metadati al file (Titolo, Artista, ecc.) per i lettori musicali
                'key': 'FFmpegMetadata',
            }
        ],
        'default_search': 'ytsearch1', # Trova automaticamente il primo risultato
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Esegue la ricerca e scarica
            info_dict = ydl.extract_info(req.query, download=True)
            info = info_dict['entries'][0] if 'entries' in info_dict else info_dict
                
            # Calcola il percorso del file finale .mp3
            raw_filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(raw_filename)
            mp3_filename = base + ".mp3"
            
            if not os.path.exists(mp3_filename):
                raise HTTPException(status_code=500, detail="Errore nella conversione in MP3")
                
            filename_only = os.path.basename(mp3_filename)
            
            # Restituisce il file forzando l'intestazione 'attachment'.
            # Questo dice al frontend/browser: "Salva questo file nella cartella Download del PC dell'utente".
            return FileResponse(
                path=mp3_filename,
                media_type="audio/mpeg",
                filename=filename_only,
                headers={"Content-Disposition": f'attachment; filename="{filename_only}"'}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))