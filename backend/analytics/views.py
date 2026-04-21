"""Analytics summary views (admin-only)."""

from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import RequestLog


@api_view(['GET'])
@permission_classes([IsAdminUser])
def request_summary(request):
    """Quick aggregate of recent requests for ops sanity checking."""
    since = timezone.now() - timedelta(days=7)
    qs = RequestLog.objects.filter(created_at__gte=since)
    by_path = qs.values('path').annotate(count=Count('id'), avg_ms=Avg('duration_ms')).order_by('-count')[:50]
    by_status = qs.values('status_code').annotate(count=Count('id')).order_by('status_code')
    return Response({
        'window_days': 7,
        'total': qs.count(),
        'by_path': list(by_path),
        'by_status': list(by_status),
    })
