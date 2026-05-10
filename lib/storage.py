import os
import uuid
import logging
from supabase import create_client

logger = logging.getLogger('IAMSTECH_STORAGE')

# Configuration from environment
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = (
    os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or
    os.environ.get('SUPABASE_SERVICE_KEY') or
    os.environ.get('SUPABASE_KEY') or
    os.environ.get('SUPABASE_ANON_KEY')
)
SUPABASE_BUCKET = os.environ.get('SUPABASE_BUCKET', 'ianstechlib')
SUPABASE_STORAGE_PUBLIC = os.environ.get('SUPABASE_STORAGE_PUBLIC', 'true').lower() in ('1', 'true', 'yes')

_supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")

def upload_to_bucket(file_bytes, filename, content_type=None, folder="uploads"):
    """
    Uploads bytes to Supabase Storage and returns the public URL.
    Ensures media persistence on ephemeral filesystems like Railway.
    """
    if not _supabase:
        logger.warning("Supabase not configured. Falling back to None.")
        return None

    # Generate unique filename to prevent collisions
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'bin'
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    storage_path = f"{folder}/{unique_filename}".lstrip('/')

    try:
        # Perform upload
        _supabase.storage.from_(SUPABASE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type} if content_type else None
        )
        
        # Return Public URL
        if SUPABASE_STORAGE_PUBLIC:
            return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{storage_path}"
        else:
            # Fallback to signed URL if bucket is private
            response = _supabase.storage.from_(SUPABASE_BUCKET).create_signed_url(storage_path, 3600*24*365)
            return response.get('signedURL')
            
    except Exception as e:
        logger.error(f"Cloud upload failed for {storage_path}: {e}")
        return None
