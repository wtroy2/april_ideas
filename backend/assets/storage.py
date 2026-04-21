"""
GCS helper functions — direct uploads, signed URLs, bucket transfers.

Mirrors the three-bucket pipeline from RateRail:
  unscanned → quarantine (after ClamAV scan) → clean
For Critter, user-uploaded pet photos go through this pipeline. Generated
videos go directly to the clean bucket since we produced them.
"""

import logging
import uuid

from django.conf import settings
from google.cloud import storage as gcs

logger = logging.getLogger('assets')


def get_gcs_client():
    """Return a configured GCS client using the service account from settings."""
    creds = getattr(settings, 'GS_CREDENTIALS', None)
    if creds:
        return gcs.Client(credentials=creds, project=settings.GOOGLE_CLOUD_PROJECT_ID)
    return gcs.Client(project=settings.GOOGLE_CLOUD_PROJECT_ID)


def upload_bytes(bucket_name, object_key, data, content_type='application/octet-stream'):
    """Upload raw bytes to GCS and return the gs:// URI."""
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_key)
    blob.upload_from_string(data, content_type=content_type)
    return f'gs://{bucket_name}/{object_key}'


def upload_file(bucket_name, object_key, file_obj, content_type=None):
    """Upload a Django UploadedFile (or any file-like) to GCS."""
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_key)
    if content_type:
        blob.upload_from_file(file_obj, content_type=content_type)
    else:
        blob.upload_from_file(file_obj)
    return f'gs://{bucket_name}/{object_key}'


def move_blob(src_bucket, src_key, dst_bucket, dst_key):
    """Copy + delete to relocate an object across buckets."""
    client = get_gcs_client()
    src = client.bucket(src_bucket).blob(src_key)
    dst = client.bucket(dst_bucket)
    new_blob = client.bucket(src_bucket).copy_blob(src, dst, dst_key)
    src.delete()
    return new_blob


def delete_blob(bucket_name, object_key):
    client = get_gcs_client()
    blob = client.bucket(bucket_name).blob(object_key)
    blob.delete()


def generate_signed_url(bucket_name, object_key, expires_seconds=3600):
    """Generate a v4 signed URL valid for `expires_seconds`."""
    from datetime import timedelta
    client = get_gcs_client()
    blob = client.bucket(bucket_name).blob(object_key)
    return blob.generate_signed_url(
        version='v4',
        expiration=timedelta(seconds=expires_seconds),
        method='GET',
    )


def make_object_key(org_id, kind, original_filename=''):
    """
    Build a stable, namespaced GCS object key.
    Example: org/123/subject_photo/8d2b3.../IMG_1234.jpg
    """
    ext = ''
    if original_filename and '.' in original_filename:
        ext = '.' + original_filename.rsplit('.', 1)[1].lower()[:8]
    return f'org/{org_id}/{kind}/{uuid.uuid4().hex}{ext}'
