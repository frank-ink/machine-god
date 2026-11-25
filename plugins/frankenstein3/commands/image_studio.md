---
description: Open the ChatGPT image studio (create an image, mark regions, edit) or generate/edit through the CLI
argument-hint: [Prompt | edit NAME --region x,y,w,h:Text]
---
Image studio (`image_studio`, service `omega-bildstudio`, loopback only). Arguments: $ARGUMENTS

1. Without arguments: run `image_studio url` (Bash; starts the service when needed, prints a one-time URL valid for 90 s) and open this URL in the browser pane with `mcp__Claude_Browser__preview_start` (parameter `url`). Do not print or store the URL any further. Then say in one sentence that the studio is open (Create / Edit / Info on the right, brush/rectangle/lasso in the image).
2. With prompt text: `image_studio generate "<text>"` (Bash, takes about 1 minute; run in the background if more than 2 minutes are expected). Output = absolute file path; show the image with Read. Then offer to open it in the studio (`image_studio url <NAME>`).
3. With `edit NAME --region x,y,w,h[:text]` (several `--region` allowed, percentages allowed): run `image_studio edit ...` and print the path.
4. Name errors first (exit 2 = ChatGPT returned no image, relay `ChatGPT says:`; exit 3 = wait timeout; service problems: `image_studio status`).

Rules: the ChatGPT account/window belongs to Gabriel: send only the image prompts the studio provides; do not log in or change anything. No screenshots (retina rule): check the studio state through page text/read_page. Prompt improvement (`image_studio polish`) runs through the free pool (0 Claude tokens).
