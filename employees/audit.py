import json
import logging

logger = logging.getLogger('employees')


def _request_meta(request):
    """Return (ip_address, user_agent, path) captured from a request."""
    ip_address = user_agent = path = ''
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR') or ''
        user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:300]
        path = request.path[:300]
    return ip_address, user_agent, path


def log_audit(user=None, action='', model_name='', object_id='', description='',
              request=None, severity='info', outcome='', category=''):
    from .models import AuditLog
    ip_address, user_agent, path = _request_meta(request)

    entry = AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=str(object_id),
        description=description,
        ip_address=ip_address or None,
        severity=severity,
        outcome=outcome,
        category=category,
        user_agent=user_agent,
        path=path,
    )
    logger.info(json.dumps({
        'user': getattr(user, 'username', None),
        'action': action,
        'model': model_name,
        'object_id': str(object_id),
        'ip': ip_address,
        'severity': severity,
        'outcome': outcome,
        'description': description,
    }, default=str))
    _evaluate_soc(entry)
    return entry


def _evaluate_soc(entry):
    try:
        from soc.engine import evaluate_event
        evaluate_event(entry)
    except Exception:
        logger.exception('SOC evaluation failed for audit event %s', entry.pk)
