import hashlib
import base64
import os
import json
import urllib.request

DEFAULT_STORAGE_DIR = "data/images"
INDEX_FILE = "image_index.json"


class ImageManager:
    """Downloads, stores, and serves images for the agent.

    Images are saved as ``<md5_hash>.jpg`` inside *storage_dir*.
    A JSON index (``image_index.json``) maps hashes to file metadata.
    """

    def __init__(self, storage_dir: str = DEFAULT_STORAGE_DIR) -> None:
        self.storage_dir = storage_dir
        self.index_path = os.path.join(self.storage_dir, INDEX_FILE)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._index: dict[str, dict] = self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_image_from_url(self, url: str) -> str:
        """Download an image from *url*, store it locally, return its MD5 hash."""
        image_bytes = self._download(url)
        image_hash = hashlib.md5(image_bytes).hexdigest()

        if image_hash in self._index:
            return image_hash  # already stored

        filename = f"{image_hash}.jpg"
        filepath = os.path.join(self.storage_dir, filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        self._index[image_hash] = {
            "filename": filename,
            "path": filepath,
        }
        self._save_index()
        return image_hash

    def save_image_from_bytes(self, data: bytes, ext: str = "png") -> str:
        """Save raw image *data* locally and return its MD5 hash."""
        image_hash = hashlib.md5(data).hexdigest()

        if image_hash in self._index:
            return image_hash  # already stored

        filename = f"{image_hash}.{ext}"
        filepath = os.path.join(self.storage_dir, filename)

        with open(filepath, "wb") as f:
            f.write(data)

        self._index[image_hash] = {
            "filename": filename,
            "path": filepath,
        }
        self._save_index()
        return image_hash

    def get_image_path(self, image_hash: str) -> str | None:
        """Return the file path for the given hash, or ``None``."""
        entry = self._index.get(image_hash)
        if entry:
            return entry["path"]
        return None

    def get_image_base64(self, image_hash: str) -> str | None:
        """Read the image file and return its Base64-encoded string."""
        path = self.get_image_path(image_hash)
        if path is None or not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _download(url: str) -> bytes:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TinyAgent/1.0)",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def _load_index(self) -> dict:
        if os.path.isfile(self.index_path):
            try:
                with open(self.index_path, "r") as f:
                    return json.load(f)
            except (IOError, json.JSONDecodeError):
                pass
        return {}

    def _save_index(self) -> None:
        with open(self.index_path, "w") as f:
            json.dump(self._index, f, indent=2, ensure_ascii=False)
