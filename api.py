from fastapi import FastAPI, HTTPException  
from fastapi.responses import JSONResponse  
from pydantic import BaseModel  
from typing import Any, Optional  
from urllib.parse import urlparse, parse_qs  
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled  
from pytube import Playlist  
import yt_dlp  
import os  
import uvicorn  
  
app = FastAPI()  
  
# Models for request payloads  
class URLRequest(BaseModel):  
    url: str  
  
class AudioDownloadRequest(BaseModel):  
    youtube_url: str  
    output_filename: str = "extracted_audio.mp3"  
    ffmpeg_location: str = None  
  
class VideoDownloadRequest(BaseModel):  
    youtube_url: str  
    output_path: str = "."  
    ffmpeg_path: str = None  
  
@app.get("/healthcheck")  
def healthcheck():  
    return {"status": "ok"}  
  
@app.post("/process-url/")  
def on_request_v1(req: URLRequest) -> Any:  
    try:  
        # Parse the request body  
        url_request = req.url  
        # Process the URL  
        response_data = process_url(url_request)  
        print(response_data)  
        # Return the response as JSON  
        return response_data  
    except Exception as e:  
        return {"error": str(e)}  
  
def process_url(url: str):  
    try:  
        if "youtube.com" in url or "youtu.be" in url:  
            if "list=" in url:  
                result = process_youtube_playlist_url(url)  
            else:  
                result = process_youtube_url(url)  
            return result  
        else:  
            raise Exception("Non-YouTube URL")  
    except Exception as e:  
        raise Exception(f"Error processing URL: {str(e)}")  
  
def process_youtube_playlist_url(url: str):  
    try:  
        playlist = Playlist(url)  
        documents = []  
        for url in playlist.video_urls:  
            print('check_url', url)  
            video_id = extract_video_id(url)  
            if not video_id:  
                raise ValueError("Invalid YouTube URL")  
            try:  
                # Attempt to fetch the transcript in English (en)  
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])  
            except NoTranscriptFound:  
                # If English transcript not found, check the available transcripts  
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)  
                transcript = None  
                if transcript_list:  
                    for t in transcript_list:  
                        if t.language_code == 'en-GB':  # Fetch en-GB if available  
                            transcript = t.fetch()  
                            break  
                        elif t.is_generated or t.language_code:  # Fallback to any language  
                            transcript = t.fetch()  
                            break  
            except TranscriptsDisabled as e:  
                print(f"Skipping video due to disabled subtitles: {e}")  
            except Exception as e:  
                print(f"Error processing video {url}: {e}")  
            transcript_full = ' '.join([i['text'] for i in transcript])  
            documents.append({"page_content": transcript_full, "metadata": {"source": url}})  
        return {"documents": documents}  
    except Exception as e:  
        raise Exception(f"Error processing YouTube playlist URL: {str(e)}")  
  
def process_youtube_url(url: str):  
    try:  
        video_id = extract_video_id(url)  
        if not video_id:  
            raise ValueError("Invalid YouTube URL")  
        try:  
            # Attempt to fetch the transcript in English (en)  
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])  
        except NoTranscriptFound:  
            # If English transcript not found, check the available transcripts  
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)  
            transcript = None  
            if transcript_list:  
                for t in transcript_list:  
                    if t.language_code == 'en-GB':  # Fetch en-GB if available  
                        transcript = t.fetch()  
                        break  
                    elif t.is_generated or t.language_code:  # Fallback to any language  
                        transcript = t.fetch()  
                        break  
        except TranscriptsDisabled as e:  
            print(f"Skipping video due to disabled subtitles: {e}")  
        except Exception as e:  
            print(f"Error processing video {url}: {e}")  
        # Combine transcript text  
        transcript_full = ' '.join([i['text'] for i in transcript])  
        return {"documents": [{"page_content": transcript_full, "metadata": {"source": url}}]}  
    except Exception as e:  
        raise Exception(f"Error processing YouTube URL: {str(e)}")  
  
def extract_video_id(url: str) -> Optional[str]:  
    # For youtu.be URLs  
    if "youtu.be" in url:  
        return url.split("/")[-1]  
    # For youtube.com URLs  
    parsed_url = urlparse(url)  
    if parsed_url.hostname in ("www.youtube.com", "youtube.com"):  
        if parsed_url.path == "/watch":  
            return parse_qs(parsed_url.query).get("v", [None])[0]  
        elif parsed_url.path.startswith(("/embed/", "/v/")):  
            return parsed_url.path.split("/")[2]  
    # If no valid YouTube URL format is found  
    return None  
  
# yt_dlp Helper Functions  
def download_audio_as_mp3(youtube_url, output_filename="extracted_audio.mp3", ffmpeg_location=None):  
    """Download the best audio stream from a YouTube video and convert it to MP3."""  
    ydl_opts = {  
        'format': 'bestaudio/best',  
        'outtmpl': output_filename,  
        'noplaylist': True,  
        'postprocessors': [{  
            'key': 'FFmpegExtractAudio',  
            'preferredcodec': 'mp3',  
            'preferredquality': '320',  
        }],  
    }  
    if ffmpeg_location:  
        ydl_opts['ffmpeg_location'] = ffmpeg_location  
  
    try:  
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
            ydl.download([youtube_url])  
        return f"Audio downloaded and converted to MP3: {output_filename}"  
    except Exception as e:  
        raise HTTPException(status_code=500, detail=str(e))  
  
def download_progress(d):  
    """Track download progress."""  
    if d['status'] == 'finished':  
        print('Download complete')  
    elif d['status'] == 'downloading':  
        downloaded_bytes = d.get('downloaded_bytes', 0)  
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)  
        if total_bytes > 0:  
            percent = downloaded_bytes * 100 / total_bytes  
            print(f'Downloading: {percent:.1f}%')  
  
def download_highest_quality(url, output_path='.', ffmpeg_path=None):  
    """Download a YouTube video in the highest available quality."""  
    ydl_opts = {  
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  
        'outtmpl': os.path.join(output_path, 'downloaded_video.%(ext)s'),  
        'merge_output_format': 'mp4',  
        'nooverwrites': True,  
        'no_color': True,  
        'progress_hooks': [download_progress]  
    }  
  
    if ffmpeg_path:  
        ydl_opts['ffmpeg_location'] = ffmpeg_path  
  
    try:  
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
            ydl.download([url])  
        return "Video downloaded as downloaded_video.mp4"  
    except Exception as e:  
        raise HTTPException(status_code=500, detail=str(e))  
  
# yt_dlp Endpoints  
@app.post("/download-audio/")  
async def download_audio(request: AudioDownloadRequest):  
    """Endpoint to download the best audio stream as an MP3 file."""  
    response = download_audio_as_mp3(  
        youtube_url=request.youtube_url,  
        output_filename=request.output_filename,  
        ffmpeg_location=request.ffmpeg_location  
    )  
    return {"message": response}  
  
@app.post("/download-video/")  
async def download_video(request: VideoDownloadRequest):  
    """Endpoint to download the highest quality video."""  
    response = download_highest_quality(  
        url=request.youtube_url,  
        output_path=request.output_path,  
        ffmpeg_path=request.ffmpeg_path  
    )  
    return {"message": response}  
  
# Main entry point  
if __name__ == "__main__":  
    uvicorn.run(app, host="0.0.0.0", port=8080)  
