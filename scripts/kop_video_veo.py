# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Makes the clip for the card at the top of the site with Veo, Google's
video model, from the approved photo (docs/design/ronde-9/video-kop.md).
Costs money on the Google account of the key: Veo is paid per second of
video. Run it yourself, with your own key in the environment:

    GEMINI_API_KEY=… uv run python scripts/kop_video_veo.py [<model>]

Without a model it takes the newest Veo model the key may use. The clip
lands in ~/Downloads/huismus-kop-veo-<n>.mp4; nothing goes into the repo.
"""

import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"
ROOT = Path(__file__).resolve().parent.parent
PHOTO = ROOT / "docs" / "design" / "ronde-7" / "fotos" / "foto-1-kop-leeg-scherm.jpg"
PROMPT = (
    "Use this photo as the first frame. Locked-off camera on a tripod: no camera movement, "
    "no zoom, no pan. The woman keeps sanding the chair leg with slow, steady strokes; her "
    "hands, arms and shoulders move naturally. Fine sawdust drifts through the window light. "
    "Everything else stays exactly where it is: the laptop and its plain light grey screen, "
    "the mug, the workbench, the tools. Nothing new appears, no text, no logos, she does not "
    "look at the camera. Documentary, natural window light, 35mm film grain, same colours as "
    "the photo. The last frame should match the first so it can loop."
)


def _call(method: str, url: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("x-goog-api-key", key)
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def newest_veo(key: str) -> str:
    models = _call("GET", f"{API}/models?pageSize=1000", key).get("models", [])
    veo = sorted(m["name"] for m in models if "veo" in m["name"])
    if not veo:
        sys.exit("Deze sleutel mag geen Veo-model gebruiken.")
    print("Veo-modellen:", ", ".join(veo))
    return veo[-1]


def main() -> None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("Zet eerst GEMINI_API_KEY in je terminal.")
    model = sys.argv[1] if len(sys.argv) > 1 else newest_veo(key)
    model = model if model.startswith("models/") else f"models/{model}"
    image = base64.b64encode(PHOTO.read_bytes()).decode()
    body = {
        "instances": [
            {"prompt": PROMPT, "image": {"bytesBase64Encoded": image, "mimeType": "image/jpeg"}}
        ],
        "parameters": {"aspectRatio": "16:9", "sampleCount": 1},
    }
    print(f"Bezig met {model} …")
    operation = _call("POST", f"{API}/{model}:predictLongRunning", key, body)
    while not operation.get("done"):
        time.sleep(10)
        operation = _call("GET", f"{API}/{operation['name']}", key)
        print("  nog bezig …")
    if "error" in operation:
        sys.exit(f"Mislukt: {operation['error']}")
    samples = operation["response"]["generateVideoResponse"]["generatedSamples"]
    downloads = Path.home() / "Downloads"
    for sample in samples:
        n = 1
        while (target := downloads / f"huismus-kop-veo-{n}.mp4").exists():
            n += 1
        request = urllib.request.Request(sample["video"]["uri"])
        request.add_header("x-goog-api-key", key)
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
        print(f"Klaar: {target}")


if __name__ == "__main__":
    main()
