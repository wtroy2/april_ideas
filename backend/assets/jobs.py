"""
RQ jobs for the assets pipeline.

  - scan_asset: ClamAV scan an unscanned upload, then move to clean or quarantine.

In dev (ENABLE_CLAMAV_SCANNING=False) the upload service skips this and writes
straight to the clean bucket; this job is only invoked when scanning is on.
"""

import logging
import requests

from django.conf import settings
from django.utils import timezone
from django_rq import job

from .models import Asset, AssetStatus
from .storage import move_blob, get_gcs_client

logger = logging.getLogger('assets')


@job('default', timeout=300)
def scan_asset(asset_id):
    """
    Scan an asset using the ClamAV scanner service, then move it to either
    the clean bucket (pass) or the quarantine bucket (fail).
    """
    try:
        asset = Asset.objects.get(id=asset_id)
    except Asset.DoesNotExist:
        logger.warning(f'scan_asset: asset {asset_id} not found')
        return

    asset.status = AssetStatus.SCANNING
    asset.scan_started_at = timezone.now()
    asset.save(update_fields=['status', 'scan_started_at', 'updated_at'])

    scanner_url = getattr(settings, 'CLAMAV_SCANNER_URL', '')
    if not scanner_url:
        logger.warning(f'scan_asset: CLAMAV_SCANNER_URL not configured, marking as passed')
        return _mark_clean(asset, 'no scanner configured (dev)')

    # Fetch the file bytes from GCS and POST to the scanner
    try:
        client = get_gcs_client()
        blob = client.bucket(asset.bucket).blob(asset.object_key)
        data = blob.download_as_bytes()
    except Exception as e:
        logger.error(f'scan_asset: failed to download {asset.uuid}: {e}')
        if getattr(settings, 'FAIL_CLOSED_ON_SCAN_ERROR', True):
            return _mark_quarantined(asset, f'download error: {e}')
        return _mark_clean(asset, f'download error (fail-open): {e}')

    try:
        response = requests.post(
            scanner_url,
            files={'file': (asset.original_filename or 'upload', data, asset.content_type)},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        if result.get('infected'):
            return _mark_quarantined(asset, result.get('virus', 'infected'))
        return _mark_clean(asset, 'clean')
    except Exception as e:
        logger.error(f'scan_asset: scanner error for {asset.uuid}: {e}')
        if getattr(settings, 'FAIL_CLOSED_ON_SCAN_ERROR', True):
            return _mark_quarantined(asset, f'scanner error: {e}')
        return _mark_clean(asset, f'scanner error (fail-open): {e}')


def _mark_clean(asset, note):
    """Move asset to clean bucket and mark READY."""
    if asset.bucket != settings.GS_CLEAN_BUCKET_NAME:
        try:
            new_key = asset.object_key  # keep same key
            move_blob(asset.bucket, asset.object_key, settings.GS_CLEAN_BUCKET_NAME, new_key)
            asset.bucket = settings.GS_CLEAN_BUCKET_NAME
            asset.object_key = new_key
        except Exception as e:
            logger.error(f'_mark_clean: move failed for {asset.uuid}: {e}')

    asset.status = AssetStatus.READY
    asset.scan_completed_at = timezone.now()
    asset.scan_result = note[:200]
    asset.save()
    logger.info(f'Asset {asset.uuid} cleared scan: {note}')


def _mark_quarantined(asset, reason):
    """Move asset to quarantine bucket and mark QUARANTINED."""
    try:
        new_key = asset.object_key
        move_blob(asset.bucket, asset.object_key,
                  settings.GS_QUARANTINE_BUCKET_NAME, new_key)
        asset.bucket = settings.GS_QUARANTINE_BUCKET_NAME
        asset.object_key = new_key
    except Exception as e:
        logger.error(f'_mark_quarantined: move failed for {asset.uuid}: {e}')

    asset.status = AssetStatus.QUARANTINED
    asset.scan_completed_at = timezone.now()
    asset.scan_result = f'quarantined: {reason}'[:200]
    asset.save()
    logger.warning(f'Asset {asset.uuid} quarantined: {reason}')
