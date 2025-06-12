import os
from urllib.parse import urljoin
from django.conf import settings
from django.core.files.storage import Storage
from supabase import create_client, Client
from storage3.utils import StorageException

class SupabaseStorage(Storage):
    """
    Custom storage backend for Supabase Storage
    """
    def __init__(self, bucket_name=None):
        # Initialize Supabase client
        supabase_url = os.environ.get('SUPABASE_URL', '')
        supabase_key = os.environ.get('SUPABASE_ANON_KEY', '')
        
        self.client: Client = create_client(supabase_url, supabase_key)
        self.bucket_name = bucket_name
    
    def _get_storage(self):
        return self.client.storage.from_(self.bucket_name)
    
    def _open(self, name, mode='rb'):
        """
        Retrieve the file from Supabase Storage
        """
        try:
            # Get the file contents
            response = self._get_storage().download(name)
            
            # Create a file-like object
            from django.core.files.base import ContentFile
            return ContentFile(response)
        except StorageException as e:
            # Handle error, e.g., file not found
            raise FileNotFoundError(f"File {name} not found in bucket {self.bucket_name}")

    def _save(self, name, content):
        """
        Save the file to Supabase Storage
        """
        try:
            # Get the content as bytes
            file_content = content.read()
            
            # Upload to Supabase
            result = self._get_storage().upload(name, file_content)
            
            # Return the file path that was saved
            return name
        except StorageException as e:
            # Handle upload error
            raise IOError(f"Error saving file to Supabase Storage: {e}")

    def delete(self, name):
        """
        Delete the file from Supabase Storage
        """
        try:
            self._get_storage().remove([name])
        except StorageException:
            # File doesn't exist, pass silently
            pass

    def exists(self, name):
        """
        Check if a file exists in Supabase Storage
        """
        try:
            # List files with the given name
            files = self._get_storage().list(name.rsplit('/', 1)[0] if '/' in name else '')
            return any(file['name'] == name.split('/')[-1] for file in files)
        except StorageException:
            return False

    def url(self, name):
        """
        Return the public URL for a file
        """
        try:
            return self._get_storage().get_public_url(name)
        except StorageException:
            return None

    def size(self, name):
        """
        Return the size of a file
        """
        try:
            files = self._get_storage().list(name.rsplit('/', 1)[0] if '/' in name else '')
            for file in files:
                if file['name'] == name.split('/')[-1]:
                    return file.get('metadata', {}).get('size', 0)
            return 0
        except StorageException:
            return 0

    def get_accessed_time(self, name):
        return None  # Not supported by Supabase Storage

    def get_created_time(self, name):
        return None  # Not supported by Supabase Storage

    def get_modified_time(self, name):
        return None  # Not supported by Supabase Storage


class ImageStorage(SupabaseStorage):
    """
    Storage for images using the 'images' bucket
    """
    def __init__(self):
        super().__init__(bucket_name='images')


class VideoStorage(SupabaseStorage):
    """
    Storage for videos using the 'videos' bucket
    """
    def __init__(self):
        super().__init__(bucket_name='videos')


class VoiceStorage(SupabaseStorage):
    """
    Storage for audio files using the 'voices' bucket
    """
    def __init__(self):
        super().__init__(bucket_name='voices')
