import os
import uuid
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

    def _ensure_folder_exists(self, path):
        """
        Ensure that a folder exists in the bucket
        Supabase requires folders to exist before files can be uploaded to them
        """
        if '/' in path:
            folder_path = path.rsplit('/', 1)[0] + '/'
            try:
                # Check if folder exists by listing with prefix
                folders = self._get_storage().list(path=folder_path)
                # If we get here, the folder likely exists already
            except StorageException:
                # Try to create the folder with an empty placeholder file
                try:
                    self._get_storage().upload(folder_path + '.placeholder', b'')
                except StorageException as e:
                    # If folder already exists or we can't create it, just log and continue
                    print(f"Note: Could not verify/create folder {folder_path}: {e}")
    
    def _save(self, name, content):
        """
        Save the file to Supabase Storage in the appropriate folder path
        """
        try:
            # Get the content as bytes
            file_content = content.read()
            
            # Ensure the folder exists before uploading (if there's a path)
            if '/' in name:
                self._ensure_folder_exists(name)
            
            # Upload to Supabase with the full path
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
            # Get folder path and filename
            if '/' in name:
                folder_path = name.rsplit('/', 1)[0]
                filename = name.split('/')[-1]
                # List files in the specific folder
                files = self._get_storage().list(folder_path)
            else:
                # Files at bucket root
                files = self._get_storage().list()
                filename = name
                
            # Check if file exists in the folder
            return any(file['name'] == filename for file in files)
        except StorageException:
            return False

    def url(self, name):
        """
        Return the public URL for a file
        """
        try:
            # Always try with the full path first (including folder structure)
            return self._get_storage().get_public_url(name)
        except StorageException as e:
            try:
                # As fallback, try with just the filename
                if '/' in name:
                    filename = name.split('/')[-1]
                    return self._get_storage().get_public_url(filename)
                else:
                    # Already tried with the name, so it truly failed
                    return None
            except StorageException:
                return None

    def size(self, name):
        """
        Return the size of a file
        """
        try:
            # Get folder path and filename
            if '/' in name:
                folder_path = name.rsplit('/', 1)[0]
                filename = name.split('/')[-1]
                # List files in the specific folder
                files = self._get_storage().list(folder_path)
            else:
                # Files at bucket root
                files = self._get_storage().list()
                filename = name
                
            # Find the file and get its size
            for file in files:
                if file['name'] == filename:
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
