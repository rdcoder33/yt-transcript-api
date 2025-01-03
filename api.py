from pydantic import BaseModel
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from youtube_transcript_api._errors import NoTranscriptFound
from urllib.parse import urlparse, parse_qs
import json
from pytube import Playlist
from typing import Any
import re

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

from fastapi import FastAPI, HTTPException  
from fastapi.responses import JSONResponse  

import uvicorn   
 
app = FastAPI()  
  
class URLRequest(BaseModel):  
    url: str  

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
        url = url
        if "youtube.com" in url or "youtu.be" in url:
            if "list=" in url:
                result = process_youtube_playlist_url(url)
            else:
                result = process_youtube_url(url)
            return result
        else:
             
            raise Exception("Non youtube URL")
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
                transcript = YouTubeTranscriptApi.get_transcript(
                    video_id, languages=['en'])
            except NoTranscriptFound:
                # If English transcript not found, check the available transcripts
                transcript_list = YouTubeTranscriptApi.list_transcripts(
                    video_id)
                transcript = None

                if transcript_list:

                    for t in transcript_list:
                        if t.language_code == 'en-GB':  # Fetch en-GB if available
                            transcript = t.fetch()
                            break
                        elif t.is_generated or t.language_code:  # Fallback to any language
                            transcript = t.fetch()  # Fetch in the available language
                            break

            except TranscriptsDisabled as e:
                print(f"Skipping video due to disabled subtitles: {e}")
            except Exception as e:
                print(f"Error processing video {url}: {e}")

            transcript_full = ' '.join([i['text'] for i in transcript])
            documents.append({"page_content": transcript_full,
                             "metadata": {"source": url}})

            # transcript = YouTubeTranscriptApi.get_transcript(video_id)
            # transcript_full = ' '.join([i['text'] for i in transcript])
            # documents.append({"page_content": transcript_full, "metadata": {"source": url}})

        return {"documents": documents}

    except Exception as e:
        raise Exception(f"Error processing YouTube URL: {str(e)}")


def process_youtube_url(url: str):
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise ValueError("Invalid YouTube URL")

        try:
            # Attempt to fetch the transcript in English (en)
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id, languages=['en'])
        except NoTranscriptFound:
            # If English transcript not found, check the available transcripts
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Look for en-GB or other available transcripts
            transcript = None
            if transcript_list:
                for t in transcript_list:
                    if t.language_code == 'en-GB':  # Fetch en-GB if available
                        transcript = t.fetch()
                        break
                    elif t.is_generated or t.language_code:  # Fallback to any language
                        transcript = t.fetch()  # Fetch in the available language
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

if __name__ == "__main__":  
    uvicorn.run(app, host="0.0.0.0", port=8080)