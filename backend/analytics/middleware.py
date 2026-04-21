"""Request-tracing middleware — samples requests and writes to RequestLog."""

import time
import random
import logging

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class AnalyticsMiddleware(MiddlewareMixin):
    """Logs a sampled fraction of requests asynchronously (best-effort, never blocks)."""

    def process_request(self, request):
        request._analytics_start = time.monotonic()
        return None

    def process_response(self, request, response):
        if not getattr(settings, 'ANALYTICS_LOG_REQUESTS', True):
            return response

        start = getattr(request, '_analytics_start', None)
        if start is None:
            return response

        sampling_rate = getattr(settings, 'ANALYTICS_SAMPLING_RATE', 1.0)
        if random.random() > sampling_rate:
            return response

        # Skip noise
        if request.path.startswith('/static/') or request.path.startswith('/admin/jsi18n/'):
            return response

        try:
            from .models import RequestLog
            duration_ms = int((time.monotonic() - start) * 1000)
            user = request.user if request.user.is_authenticated else None
            x = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x.split(',')[0].strip() if x else request.META.get('REMOTE_ADDR')
            RequestLog.objects.create(
                user=user,
                method=request.method,
                path=request.path[:500],
                status_code=response.status_code,
                duration_ms=duration_ms,
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )
        except Exception as e:
            logger.warning(f'AnalyticsMiddleware failed: {e}')
        return response
