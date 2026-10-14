import time
import json
from django.core.cache import cache
from django.shortcuts import redirect
from django.contrib import messages


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/login/' and request.method == 'POST':
            ip = self.get_client_ip(request)
            username = request.POST.get('username', '')
            key = f'login_attempts_{ip}'
            username_key = f'login_attempts_user_{username}'

            attempts = cache.get(key, 0)
            user_attempts = cache.get(username_key, 0)

            if attempts >= 5 or user_attempts >= 5:
                messages.error(request, 'Too many login attempts. Please wait 5 minutes and try again.')
                return redirect('login')

        response = self.get_response(request)

        if request.path == '/login/' and request.method == 'POST':
            if not request.user.is_authenticated:
                ip = self.get_client_ip(request)
                username = request.POST.get('username', '')
                key = f'login_attempts_{ip}'
                username_key = f'login_attempts_user_{username}'

                attempts = cache.get(key, 0)
                cache.set(key, attempts + 1, 300)

                user_attempts = cache.get(username_key, 0)
                cache.set(username_key, user_attempts + 1, 300)
            else:
                ip = self.get_client_ip(request)
                username = request.POST.get('username', '')
                cache.delete(f'login_attempts_{ip}')
                cache.delete(f'login_attempts_user_{username}')

        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')
