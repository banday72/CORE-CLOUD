from django.http import JsonResponse


def is_ajax(request):
    """True when the request came from the interactive UI layer (fetch)."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def json_ok(message='', **extra):
    payload = {'ok': True, 'message': message}
    payload.update(extra)
    return JsonResponse(payload)


def json_err(message='Something went wrong.', status=400, **extra):
    payload = {'ok': False, 'message': message}
    payload.update(extra)
    return JsonResponse(payload, status=status)
