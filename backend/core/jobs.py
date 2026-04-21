"""
Job dispatcher: either enqueue to RQ (production) or run in a background
thread on the same process (dev convenience).

Toggle with RUN_JOBS_INLINE=True in .env. Inline mode means:
  - No RQ worker required
  - No Redis required for jobs (still needed for cache, but that's optional)
  - No fork/gRPC segfault drama on macOS
  - Job runs in a daemon thread so HTTP response returns immediately

The thread is daemon=True so it dies with the process — fine for dev where
you don't care about durability across restarts.
"""

import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)


def run_job(queue_name, func, *args, **kwargs):
    """
    Either enqueue to RQ (default) or run in a background thread (inline mode).
    Returns the RQ job or the Thread, never blocks the caller.
    """
    if getattr(settings, 'RUN_JOBS_INLINE', False):
        def _runner():
            try:
                logger.info(f'[inline] Running {func.__module__}.{func.__name__}({args}, {kwargs})')
                func(*args, **kwargs)
                logger.info(f'[inline] Finished {func.__name__}')
            except Exception as e:
                logger.exception(f'[inline] {func.__name__} failed: {e}')
        t = threading.Thread(target=_runner, daemon=True, name=f'inline-{func.__name__}')
        t.start()
        return t

    import django_rq
    return django_rq.get_queue(queue_name).enqueue(func, *args, **kwargs)
