#!/usr/bin/env python3
"""POC: Post to Bluesky + Threads.
- Bluesky: text and optional local image (uploaded as blob).
- Threads: text (auto or two-step) and image (create IMAGE container -> publish).
- Local images are auto-uploaded to Backblaze B2 (S3-compatible) with GitHub Raw fallback.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import mimetypes
import sys
import time
import warnings
from pathlib import Path

import requests
import yaml

# silence the Field() warning the user saw elsewhere
warnings.filterwarnings(
    "ignore",
    message=r"The 'default' attribute.*`Field\(\)`",
    category=UserWarning,
)

# ---------- config ----------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"❌ config.yaml not found at {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def mode_of(cfg: dict) -> str:
    return str(cfg.get("script", {}).get("mode", "prod")).lower()


# ---------- image hosting (B2 primary, GitHub fallback) ----------
def guess_ct(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def upload_b2(b2_cfg: dict, local_path: str) -> str:
    try:
        import boto3
    except Exception:
        raise RuntimeError("Missing dependency boto3 (pip install boto3)")
    region = b2_cfg["region"]
    bucket = b2_cfg["bucket"]
    key_id = b2_cfg["access_key_id"]
    secret = b2_cfg["secret_access_key"]
    prefix = (b2_cfg.get("prefix") or "").strip("/")
    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        endpoint_url=f"https://s3.{region}.backblazeb2.com",
    )
    p = Path(local_path)
    key = f"{int(time.time())}_{p.name}"
    if prefix:
        key = f"{prefix}/{key}"
    s3.upload_file(str(p), bucket, key, ExtraArgs={"ContentType": guess_ct(p.name), "ACL": "public-read"})
    return f"https://s3.{region}.backblazeb2.com/{bucket}/{key}"


def upload_github_raw(gh_cfg: dict, local_path: str) -> str:
    token = gh_cfg["token"]
    owner = gh_cfg["owner"]
    repo = gh_cfg["repo"]
    branch = gh_cfg.get("branch", "main")
    subdir = (gh_cfg.get("subdir") or "").strip("/")
    p = Path(local_path)
    dest_rel = f"{int(time.time())}_{p.name}"
    if subdir:
        dest_rel = f"{subdir}/{dest_rel}"
    api = f"https://api.github.com/repos/{owner}/{repo}/contents/{dest_rel}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    with open(local_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    # create-or-update
    r_get = requests.get(api, headers=headers, params={"ref": branch}, timeout=30)
    payload = {"message": f"Add media {p.name}", "content": b64, "branch": branch}
    if r_get.status_code == 200:
        payload["sha"] = r_get.json().get("sha")
    r_put = requests.put(api, headers=headers, json=payload, timeout=60)
    if not (200 <= r_put.status_code < 300):
        raise RuntimeError(f"GitHub upload failed: {r_put.status_code} {r_put.text}")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{dest_rel}"


def get_public_url(cfg: dict, local_path: str) -> str:
    hosting = cfg.get("image_hosting", {}) or {}
    provider = (hosting.get("provider") or "backblaze").lower()
    primary = provider
    # choose configs
    b2_cfg = hosting.get("backblaze")
    gh_cfg = hosting.get("github")

    def try_b2():
        if not b2_cfg:
            raise RuntimeError("Backblaze not configured")
        return upload_b2(b2_cfg, local_path)

    def try_gh():
        if not gh_cfg:
            raise RuntimeError("GitHub not configured")
        return upload_github_raw(gh_cfg, local_path)

    # primary then fallback
    try:
        return try_b2() if primary == "backblaze" else try_gh()
    except Exception:
        try:
            return try_gh() if primary == "backblaze" else try_b2()
        except Exception as e2:
            raise RuntimeError(f"Both hosts failed: {e2}")


# ---------- Bluesky ----------
def post_bluesky(cfg: dict, text: str | None, image_path: str | None) -> None:
    from pathlib import Path

    from atproto import Client, client_utils, models
    from PIL import Image

    md = (cfg.get("script", {}).get("mode", "prod")).lower()
    c = cfg["bluesky"][md]
    handle = c["handle"]
    pwd = c["app_password"]
    service_url = c.get("service_url") or "https://bsky.social"

    client = Client(service_url)
    client.login(handle, pwd)

    tb = client_utils.TextBuilder()
    tb.text(text or "")

    if not image_path:
        client.send_post(tb)
        return

    # single image with aspect ratio
    with Image.open(image_path) as im:
        w, h = im.size
    ar = models.AppBskyEmbedDefs.AspectRatio(height=h, width=w)
    image_data = Path(image_path).read_bytes()

    client.send_image(
        tb,
        image=image_data,
        image_alt=Path(image_path).name,
        image_aspect_ratio=ar,
    )


# ---------- Threads Graph API ----------
THREADS_BASE = "https://graph.threads.net/v1.0"


def _safe_json(r: requests.Response):
    try:
        return r.json()
    except Exception:
        return {"raw": r.text}


def threads_me(access_token: str) -> dict:
    r = requests.get(f"{THREADS_BASE}/me", params={"access_token": access_token}, timeout=15)
    return {"status": r.status_code, "data": _safe_json(r)}


def threads_create_text(access_token: str, text: str, auto_publish: bool) -> dict:
    params = {"text": text, "media_type": "TEXT", "auto_publish_text": "true" if auto_publish else "false"}
    r = requests.post(
        f"{THREADS_BASE}/me/threads",
        params={"access_token": access_token},
        data=params,
        timeout=30,
    )
    return {"status": r.status_code, "data": _safe_json(r)}


def threads_create_image(access_token: str, text: str | None, image_url: str, alt_text: str | None) -> dict:
    params = {"media_type": "IMAGE", "image_url": image_url}
    if text:
        params["text"] = text
    if alt_text:
        params["alt_text"] = alt_text
    r = requests.post(
        f"{THREADS_BASE}/me/threads",
        params={"access_token": access_token},
        data=params,
        timeout=30,
    )
    return {"status": r.status_code, "data": _safe_json(r)}


def threads_publish(access_token: str, creation_id: str) -> dict:
    r = requests.post(
        f"{THREADS_BASE}/me/threads_publish",
        params={"access_token": access_token, "creation_id": creation_id},
        timeout=30,
    )
    return {"status": r.status_code, "data": _safe_json(r)}


def post_threads(cfg: dict, text: str | None, local_image: str | None, auto_publish_text: bool) -> None:
    md = mode_of(cfg)
    access_token = cfg["threads"][md]["access_token"]


    # If we have a local image path, convert to public URL first.
    image_url = None
    if local_image:
        if local_image.startswith("http://") or local_image.startswith("https://"):
            image_url = local_image
        else:
            image_url = get_public_url(cfg, local_image)

    if image_url:
        create = threads_create_image(access_token, text or "", image_url, alt_text=None)
        if create["status"] != 200:
            return
        creation_id = create["data"].get("id")
        if not creation_id:
            return
        pub = threads_publish(access_token, creation_id)
        if pub["status"] == 200:
            pass
        else:
            pass
        return

    # Text only
    if text:
        create = threads_create_text(access_token, text, auto_publish_text)
        if create["status"] != 200:
            return
        if auto_publish_text:
            return
        creation_id = create["data"].get("id")
        if not creation_id:
            return
        pub = threads_publish(access_token, creation_id)
        if pub["status"] == 200:
            pass
        else:
            pass
    else:
        pass


# ---------- CLI ----------
def parse_args():
    ap = argparse.ArgumentParser(description="Multi-poster POC for Bluesky + Threads")
    ap.add_argument("--text", type=str, help="Text to post")
    ap.add_argument("--image", type=str, help="Local image path or hosted https URL")
    ap.add_argument("--auto-publish-text", action="store_true", help="Threads one-step text publish")
    return ap.parse_args()


def main():
    args = parse_args()
    cfg = load_config()
    mode_of(cfg)
    socials = cfg.get("socials", {}) or {}

    # Bluesky
    if socials.get("bluesky", False):
        with contextlib.suppress(Exception):
            post_bluesky(
                cfg,
                args.text,
                args.image if args.image and not args.image.startswith(("http://", "https://")) else None,
            )
    else:
        pass

    # Threads
    if socials.get("threads", False):
        with contextlib.suppress(Exception):
            post_threads(cfg, args.text, args.image, auto_publish_text=args.auto_publish_text)
    else:
        pass


if __name__ == "__main__":
    main()
