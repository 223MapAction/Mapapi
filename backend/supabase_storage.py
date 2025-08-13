# backend/supabase_storage.py
import os
from django.conf import settings
from django.core.files.storage import Storage
from django.core.files.base import ContentFile
from django.utils.deconstruct import deconstructible

from supabase import create_client, Client
from storage3.utils import StorageException


@deconstructible
class SupabaseStorage(Storage):
    """
    Custom storage backend for Supabase Storage (déconstructible).
    Ne PAS mettre d'objet client dans __init__.
    """
    def __init__(
        self,
        bucket_name=None,
        url_env="SUPABASE_URL",
        key_env="SUPABASE_ANON_KEY",
        signed_url_expiry=60 * 60 * 24 * 365,  # 1 an
    ):
        # ⚠️ Uniquement des types simples ici
        self.bucket_name = bucket_name
        self.url_env = url_env
        self.key_env = key_env
        self.signed_url_expiry = signed_url_expiry
        # client non initialisé ici (lazy)

    # Client Supabase créé à la volée (lazy) et non sérialisé dans la migration
    @property
    def client(self) -> Client:
        supabase_url = os.environ.get(self.url_env, "")
        supabase_key = os.environ.get(self.key_env, "")
        if not supabase_url or not supabase_key:
            raise RuntimeError("SUPABASE_URL/SUPABASE_ANON_KEY non définis dans l'environnement.")
        return create_client(supabase_url, supabase_key)

    def _get_storage(self):
        if not self.bucket_name:
            raise RuntimeError("bucket_name non défini pour SupabaseStorage")
        return self.client.storage.from_(self.bucket_name)

    # Déconstruction explicite (facultative avec @deconstructible mais plus sûr)
    def deconstruct(self):
        path = "backend.supabase_storage.SupabaseStorage"
        args = []
        kwargs = {
            "bucket_name": self.bucket_name,
            "url_env": self.url_env,
            "key_env": self.key_env,
            "signed_url_expiry": self.signed_url_expiry,
        }
        return (path, args, kwargs)

    def _open(self, name, mode="rb"):
        try:
            response = self._get_storage().download(name)
            return ContentFile(response)
        except StorageException:
            raise FileNotFoundError(f"File {name} not found in bucket {self.bucket_name}")

    def _ensure_folder_exists(self, path):
        if "/" in path:
            folder_path = path.rsplit("/", 1)[0] + "/"
            try:
                _ = self._get_storage().list(path=folder_path)
            except StorageException:
                try:
                    self._get_storage().upload(folder_path + ".placeholder", b"")
                except StorageException as e:
                    # non bloquant
                    print(f"Note: Could not verify/create folder {folder_path}: {e}")

    def _save(self, name, content):
        try:
            file_content = content.read()
            if "/" in name:
                self._ensure_folder_exists(name)
            _ = self._get_storage().upload(name, file_content)
            return name
        except StorageException as e:
            raise IOError(f"Error saving file to Supabase Storage: {e}")

    def delete(self, name):
        try:
            self._get_storage().remove([name])
        except StorageException:
            pass

    def exists(self, name):
        try:
            if "/" in name:
                folder_path = name.rsplit("/", 1)[0]
                filename = name.split("/")[-1]
                files = self._get_storage().list(folder_path)
            else:
                files = self._get_storage().list()
                filename = name
            return any((f.get("name") or f.get("Name")) == filename for f in files)
        except StorageException:
            return False

    def url(self, name):
        try:
            signed = self._get_storage().create_signed_url(name, self.signed_url_expiry)
            # selon la version, la clé peut être 'signedURL' ou 'signed_url'
            if isinstance(signed, dict):
                return signed.get("signedURL") or signed.get("signed_url") or None
            return signed  # fallback si lib renvoie directement une str
        except StorageException:
            # essai fallback naïf (inutile si path correct)
            try:
                filename = name.split("/")[-1]
                signed = self._get_storage().create_signed_url(filename, self.signed_url_expiry)
                if isinstance(signed, dict):
                    return signed.get("signedURL") or signed.get("signed_url") or None
                return signed
            except StorageException:
                return None

    def size(self, name):
        try:
            if "/" in name:
                folder_path = name.rsplit("/", 1)[0]
                filename = name.split("/")[-1]
                files = self._get_storage().list(folder_path)
            else:
                files = self._get_storage().list()
                filename = name
            for f in files:
                if (f.get("name") or f.get("Name")) == filename:
                    meta = f.get("metadata") or f.get("Metadata") or {}
                    return meta.get("size") or meta.get("Size") or 0
            return 0
        except StorageException:
            return 0

    def get_accessed_time(self, name):
        return None

    def get_created_time(self, name):
        return None

    def get_modified_time(self, name):
        return None


@deconstructible
class ImageStorage(SupabaseStorage):
    def __init__(self, **kwargs):
        super().__init__(bucket_name="images", **kwargs)

    def deconstruct(self):
        path = "backend.supabase_storage.ImageStorage"
        return (path, [], {})  # pas d’args/kwargs car bucket fixé


@deconstructible
class VideoStorage(SupabaseStorage):
    def __init__(self, **kwargs):
        super().__init__(bucket_name="videos", **kwargs)

    def deconstruct(self):
        path = "backend.supabase_storage.VideoStorage"
        return (path, [], {})


@deconstructible
class VoiceStorage(SupabaseStorage):
    def __init__(self, **kwargs):
        super().__init__(bucket_name="voices", **kwargs)

    def deconstruct(self):
        path = "backend.supabase_storage.VoiceStorage"
        return (path, [], {})
