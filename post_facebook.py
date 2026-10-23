#!/usr/bin/env python3
"""Post a rendered film to the Discipline Builds Facebook Page (secrets: FB_PAGE_ID, FB_PAGE_TOKEN)."""
import json, os, sys, requests

def main(video, spec_path):
    pid, tok = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN")
    if not pid or not tok:
        print("FB secrets not set; skipping Facebook post"); return
    spec = json.load(open(spec_path))
    desc = spec["title"] + "\n\n" + spec["lines"][0][0] + "\n\nA new animated film every day. Follow Discipline Builds.\n\n#discipline #motivation #selfimprovement #mindset"
    with open(video, "rb") as f:
        r = requests.post(f"https://graph-video.facebook.com/v19.0/{pid}/videos",
            data={"access_token": tok, "title": spec["title"][:100], "description": desc},
            files={"source": f}, timeout=600)
    print(r.status_code, r.text)
    r.raise_for_status()

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
