#!/usr/bin/env python3
"""Upload a rendered film to YouTube using an OAuth refresh token (secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN)."""
import json, os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def main(video, spec_path, thumb=None):
    spec = json.load(open(spec_path))
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds)
    desc = spec.get("description") or (
        spec["lines"][0][0] + " A short animated film about discipline, struggle and becoming the person who is already there.\n\n"
        "Discipline Builds posts a new animated film every day about discipline, ambition and becoming better. Subscribe and start your Day One.\n\n"
        "#discipline #motivation #selfimprovement #mindset #shorts #animatedfilm")
    body = {"snippet": {"title": spec["title"][:100] + (" #shorts" if "#shorts" not in spec["title"] else ""), "description": desc,
                        "tags": ["discipline", "motivation", "self improvement", "mindset", "animated short film", "shorts"],
                        "categoryId": "22", "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(video, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    print("uploaded", resp["id"])
    if thumb and os.path.exists(thumb):
        try:
            yt.thumbnails().set(videoId=resp["id"], media_body=MediaFileUpload(thumb, mimetype="image/png")).execute()
            print("thumbnail set")
        except Exception as e:  # never fail the upload because of the thumbnail
            print("thumbnail not set:", e)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
