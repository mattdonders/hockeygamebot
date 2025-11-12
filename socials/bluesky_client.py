# socials/bluesky_client.py
from __future__ import annotations

import io
import json
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from atproto import Client, client_utils
from atproto import models as at_models
from atproto_client import models as atc_models
from PIL import Image
from pytz import timezone

from socials.types import PostRef

from .base import SocialClient, SocialPost


@dataclass
class BlueskyConfig:
    handle: str
    app_password: str
    service_url: str | None = None
    session_file: str | None = None


def _parse_at_uri(uri: str) -> tuple[str, str, str]:
    """
    Parse an at:// URI:
      at://did:plc:XXXX/app.bsky.feed.post/3m4abc... -> (repo_did, collection, rkey)
    """
    if not uri.startswith("at://"):
        raise ValueError(f"Not an at:// uri: {uri}")
    parts = uri[5:].split("/")  # strip 'at://'
    if len(parts) < 3:
        raise ValueError(f"Malformed at:// uri: {uri}")
    repo_did = parts[0]
    collection = "/".join(parts[1:-1])
    rkey = parts[-1]
    return repo_did, collection, rkey


def _strong_ref(uri: str, cid: str) -> atc_models.ComAtprotoRepoStrongRef.Main:
    return atc_models.ComAtprotoRepoStrongRef.Main(uri=uri, cid=cid)


class BlueskyClient(SocialClient):
    """
    Minimal, resilient Bluesky client:
      - Restores/saves session.
      - Auto-detects facets (links, mentions, hashtags) via client_utils.RichText.
      - Handles image uploads.
      - Replies using a robust ReplyRef builder (prefers CID; falls back if needed).
    """

    def __init__(self, cfg: BlueskyConfig):
        self.cfg = cfg
        self.client = Client(cfg.service_url or "https://bsky.social")
        # Try restore; if it fails, do a fresh login.
        if not self._load_session():
            self.client.login(cfg.handle, cfg.app_password)
            self._save_session()

    # ---------------- Session helpers ----------------

    def _load_session(self) -> bool:
        sf = self.cfg.session_file
        if not sf:
            return False
        p = Path(sf)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))

            # pylint: disable=no-member  # provided by atproto client at runtime
            self.client.restore_session(data)  # type: ignore[attr-defined]

            # sanity check
            self.client.get_profile(self.cfg.handle)
            logging.info("Bluesky session restored from %s", p)
            return True
        except Exception as e:
            logging.warning("Failed to restore Bluesky session (%s). Will re-login.", e)
            return False

    def _save_session(self) -> None:
        sf = self.cfg.session_file
        if not sf:
            return
        p = Path(sf)
        p.parent.mkdir(parents=True, exist_ok=True)

        # pylint: disable=no-member  # provided by atproto client at runtime
        data = self.client.export_session()  # type: ignore[attr-defined]

        p.write_text(json.dumps(data), encoding="utf-8")
        logging.info("Bluesky session saved to %s", p)

    def login_or_restore(self) -> None:
        if not self._load_session():
            self.client.login(self.cfg.handle, self.cfg.app_password)
            self._save_session()

    # ---------------- Posting helpers ----------------

    def _facets_for_text(self, text: str) -> tuple[str, list | None]:
        """
        Build clickable facets for hashtags and URLs using client_utils.RichText when available.
        Falls back silently to plain text on any error.
        """
        try:
            RT = getattr(client_utils, "RichText", None)
            if RT is None:
                return text, None
            rt = RT(text)
            # The atproto RichText can auto-detect links/mentions/hashtags when you pass the client
            rt.detect_facets(self.client)
            return rt.text, rt.facets
        except Exception:
            return text, None

    def _upload_image(self, image_path_or_list, alt_text: str | list[str] | None):
        """
        Build an embed for Bluesky images.

        - Single path -> returns AppBskyEmbedImages.Main with correct aspect ratio.
        - List/Tuple (max 4) -> returns AppBskyEmbedImages.Main containing all images.
        (We still return an embed so the caller can use `send_post(..., embed=...)`.)
        """
        # Normalize paths
        if isinstance(image_path_or_list, (list, tuple)):
            paths = list(image_path_or_list)[:4]
        else:
            paths = [image_path_or_list]

        # Normalize alt text(s)
        if isinstance(alt_text, list):
            alts = (alt_text + ["", "", "", ""])[: len(paths)]
        else:
            alts = [alt_text or ""] * len(paths)

        images: list[at_models.AppBskyEmbedImages.Image] = []

        for i, p in enumerate(paths):
            data = Path(p).read_bytes()

            # Extract dimensions for aspect ratio (falls back if PIL can’t read)
            width = height = None
            try:
                with Image.open(io.BytesIO(data)) as im:
                    width, height = im.size
            except Exception:
                pass
            if not width or not height:
                width, height = 1200, 675  # safe default 16:9

            # Upload the blob
            uploaded = self.client.upload_blob(data)

            # NOTE: AspectRatio lives under AppBskyEmbedDefs on atproto==0.0.63
            aspect = at_models.AppBskyEmbedDefs.AspectRatio(width=width, height=height)

            images.append(
                at_models.AppBskyEmbedImages.Image(
                    image=uploaded.blob,
                    alt=alts[i],
                    aspect_ratio=aspect,
                )
            )

        return at_models.AppBskyEmbedImages.Main(images=images)

    def _reply_ref_from_parent_uri(self, parent_uri: str) -> at_models.AppBskyFeedPost.ReplyRef | None:
        """
        Build a proper ReplyRef for Bluesky. Parse the at:// first to avoid the SDK
        calling getRecord with a full URI as rkey (which causes a 400).
        """
        if not parent_uri:
            return None

        # Preferred path: parse at:// and fetch the record/cid directly
        try:
            repo_did, collection, rkey = _parse_at_uri(parent_uri)
            rec = self.client.app.bsky.feed.post.get(repo_did, rkey)
            cid = getattr(rec, "cid", None)
            if cid:
                strong = _strong_ref(parent_uri, cid)
                return at_models.AppBskyFeedPost.ReplyRef(parent=strong, root=strong)
        except Exception:
            pass

        # Fallback: let the high-level helper try (may log a 400; still harmless)
        try:
            post = self.client.get_post(parent_uri)  # returns object with .cid/.uri on most versions
            if getattr(post, "cid", None):
                strong = _strong_ref(parent_uri, post.cid)
                return at_models.AppBskyFeedPost.ReplyRef(parent=strong, root=strong)
        except Exception:
            pass

        # Last resort: parent-only strong ref (empty CID). Threading might be imperfect, but it won't crash.
        try:
            strong = _strong_ref(parent_uri, "")
            return at_models.AppBskyFeedPost.ReplyRef(parent=strong, root=strong)
        except Exception:
            return None

    # ---------------- Public API ----------------
    def post(self, post: SocialPost, reply_to_ref: PostRef | None = None) -> PostRef:
        """
        Create a Bluesky post (text and optional image(s)). Returns a PostRef.
        - If local_image is a list/tuple -> send as multi-image post via embed.
        - If single image -> send with correct aspect ratio.
        """
        # 1) Text + facets
        text, facets = self._facets_for_text(post.text or "")

        # 2) Threading
        reply_ref = None
        if reply_to_ref and getattr(reply_to_ref, "uri", None):
            reply_ref = self._reply_ref_from_parent_uri(reply_to_ref.uri)

        # 3) Images
        image_payload = None
        if getattr(post, "local_images", None):
            image_payload = post.local_images
        elif getattr(post, "local_image", None):
            image_payload = post.local_image
        embed = None
        if image_payload:
            # If list/tuple -> multi-image embed (up to 4). If single -> single-image.
            embed = self._upload_image(image_payload, getattr(post, "alt_text", "") or "")

        # 4) Send (try helper; fall back to raw createRecord)
        try:
            created = self.client.send_post(
                text=text,
                embed=embed,
                facets=facets,
                reply_to=reply_ref,
            )
            uri = str(getattr(created, "uri", "") or created.get("uri"))
            cid = str(getattr(created, "cid", "") or created.get("cid"))
        except Exception:
            record = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.utcnow().isoformat() + "Z",
            }
            if facets:
                record["facets"] = facets
            if embed:
                record["embed"] = embed
            if reply_ref:
                record["reply"] = reply_ref

            did = getattr(self, "did", None) or getattr(getattr(self.client, "me", None), "did", None)
            resp = self.client.com.atproto.repo.create_record(
                data={
                    "repo": did,
                    "collection": "app.bsky.feed.post",
                    "record": record,
                }
            )
            uri = str(getattr(resp, "uri", "") or resp.get("uri"))
            cid = str(getattr(resp, "cid", "") or resp.get("cid"))

        return PostRef(
            platform="bluesky",
            id=uri,
            uri=uri,
            cid=cid or None,
            published=True,
            raw={"uri": uri, "cid": cid},
        )
