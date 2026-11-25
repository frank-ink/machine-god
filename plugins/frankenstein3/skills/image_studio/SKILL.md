---
name: image_studio
description: Create and iteratively edit images with the ChatGPT image studio (mark regions, describe, send back to ChatGPT). Use for "make an image", "edit image", "image studio", /image_studio.
---
# image_studio – ChatGPT image studio

Service `omega-bildstudio` (systemd --user, 127.0.0.1:18796), code `~/omega-browser/studio/`, CLI `bild` (= `studio/bild.py`).

## Workflow
- Open the studio: `image_studio url` -> open the URL (one-time, 90 s) in the browser pane (`preview_start` with `url`), or `image_studio` for a Chrome app window. Do not log the URL.
- Generate: `image_studio generate "Prompt" [-n 2] [--style tech-noir]` -> path(s). Takes ~1 min per image.
- Edit: `image_studio edit NAME --region 10%,20%,30%,40%:"description" [--region ...] [--general "..."]` -> path. Up to 6 regions; ChatGPT receives the original plus the marked-up version.
- More: `image_studio variation NAME`, `image_studio list [-q search]`, `image_studio show NAME` (version chain), `image_studio export NAME --fmt webp --scale 0.5 -o file`, `image_studio upload FILE`, `image_studio polish "Prompt"` (free pool), `image_studio status`.
- `--json` for machine-readable output, `--no-wait` only queues.

## Limits / rules
- Exit 2: ChatGPT returned no image (follow-up question/text) – relay the text, make the prompt more precise. Exit 3: wait timeout, the job keeps running in the studio, the image shows up later as "delivered later".
- The ChatGPT account belongs to Gabriel: no login, no settings, image prompts only.
- Every generation/edit is a real message in the ChatGPT image chat (account limits): do not fire in loops, use variants (-n) sparingly.
- No screenshots of the UI (retina rule): use page text / `read_page`.
- The studio key lives in `~/omega-browser/run/studio_key` (600): never print it.
