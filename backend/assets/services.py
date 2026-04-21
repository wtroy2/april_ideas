"""
Asset services — high-level operations for ingesting uploads and creating
records for generated outputs. These are the entry points for views and jobs.
"""

import logging
import mimetypes
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from PIL import Image

from .models import Asset, AssetKind, AssetStatus
from .storage import upload_file, upload_bytes, make_object_key, move_blob

logger = logging.getLogger('assets')


# --------------------------------------------------------------------------
# User uploads (subject photos)
# --------------------------------------------------------------------------

def ingest_user_upload(*, organization, user, uploaded_file, kind=AssetKind.SUBJECT_PHOTO):
    """
    Take a Django UploadedFile, push it to the unscanned bucket, create an
    Asset row, and (in prod) enqueue an RQ scan job. In dev with scanning
    disabled we mark it READY immediately and copy to the clean bucket.
    """
    object_key = make_object_key(organization.id, kind, uploaded_file.name)
    content_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or 'application/octet-stream'

    # Determine target bucket based on whether scanning is enabled
    scanning_enabled = getattr(settings, 'ENABLE_CLAMAV_SCANNING', False)
    if scanning_enabled:
        bucket = settings.GS_UNSCANNED_BUCKET_NAME
        initial_status = AssetStatus.UPLOADED
    else:
        # Dev: skip the quarantine pipeline, write straight to clean
        bucket = settings.GS_CLEAN_BUCKET_NAME
        initial_status = AssetStatus.READY

    upload_file(bucket, object_key, uploaded_file, content_type=content_type)

    # Read image dims (best-effort, doesn't block on failure)
    width, height = None, None
    if content_type.startswith('image/'):
        try:
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            width, height = img.size
        except Exception as e:
            logger.warning(f'Could not read image dimensions: {e}')

    asset = Asset.objects.create(
        organization=organization,
        uploaded_by=user,
        kind=kind,
        status=initial_status,
        bucket=bucket,
        object_key=object_key,
        original_filename=uploaded_file.name[:255],
        content_type=content_type,
        size_bytes=uploaded_file.size,
        width=width,
        height=height,
    )

    if scanning_enabled:
        from . import jobs
        from core.jobs import run_job
        run_job('default', jobs.scan_asset, asset.id)

    logger.info(f'Ingested upload {asset.uuid} ({kind}) into {bucket}')
    return asset


# --------------------------------------------------------------------------
# User-uploaded music tracks
# --------------------------------------------------------------------------

def ingest_audio_upload(*, organization, user, uploaded_file):
    """
    Ingest an uploaded music track. Same path as photo uploads but with
    kind=AUDIO. Skips ClamAV in dev (mp3/m4a/wav don't really need it locally).
    """
    object_key = make_object_key(organization.id, AssetKind.AUDIO, uploaded_file.name)
    content_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0] or 'audio/mpeg'

    scanning_enabled = getattr(settings, 'ENABLE_CLAMAV_SCANNING', False)
    bucket = settings.GS_UNSCANNED_BUCKET_NAME if scanning_enabled else settings.GS_CLEAN_BUCKET_NAME
    initial_status = AssetStatus.UPLOADED if scanning_enabled else AssetStatus.READY

    upload_file(bucket, object_key, uploaded_file, content_type=content_type)

    asset = Asset.objects.create(
        organization=organization,
        uploaded_by=user,
        kind=AssetKind.AUDIO,
        status=initial_status,
        bucket=bucket,
        object_key=object_key,
        original_filename=uploaded_file.name[:255],
        content_type=content_type,
        size_bytes=uploaded_file.size,
    )

    if scanning_enabled:
        from . import jobs
        from core.jobs import run_job
        run_job('default', jobs.scan_asset, asset.id)

    logger.info(f'Ingested audio upload {asset.uuid} ({uploaded_file.name})')
    return asset


# --------------------------------------------------------------------------
# Generated outputs (videos, thumbnails, audio)
# --------------------------------------------------------------------------

def register_generated_video(*, organization, video_bytes, content_type='video/mp4',
                              duration_seconds=None, width=None, height=None,
                              filename='generated.mp4'):
    """
    Save a video we generated (e.g. from Veo) to the clean bucket and create
    an Asset row. Used by the generation pipeline.
    """
    object_key = make_object_key(organization.id, AssetKind.GENERATED_VIDEO, filename)
    bucket = settings.GS_CLEAN_BUCKET_NAME
    upload_bytes(bucket, object_key, video_bytes, content_type=content_type)

    return Asset.objects.create(
        organization=organization,
        kind=AssetKind.GENERATED_VIDEO,
        status=AssetStatus.READY,
        bucket=bucket,
        object_key=object_key,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(video_bytes),
        duration_seconds=duration_seconds,
        width=width,
        height=height,
    )
