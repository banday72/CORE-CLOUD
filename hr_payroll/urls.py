from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import logout
from django.shortcuts import redirect

from employees.views import LockoutLoginView
from hr_payroll import views as core_views
from soc import views as soc_views


def custom_logout(request):
    log_audit_logout(request)
    logout(request)
    return redirect('login')


def log_audit_logout(request):
    if request.user.is_authenticated:
        from employees.audit import log_audit
        log_audit(user=request.user, action='logout', model_name='User',
                  object_id=request.user.username, description='User logged out', request=request)


urlpatterns = [
    path('', core_views.landing, name='landing'),
    path('terms/', core_views.terms, name='terms'),
    path('privacy/', core_views.privacy, name='privacy'),
    path('admin/', admin.site.urls),
    path('login/', LockoutLoginView.as_view(), name='login'),
    path('logout/', custom_logout, name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset.html',
        email_template_name='registration/password_reset_email.html',
        subject_template_name='registration/password_reset_subject.txt',
        success_url='/password-reset/done/',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url='/password-reset-complete/',
    ), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('', include('employees.urls')),
    path('attendance/', include('attendance.urls')),
    path('leaves/', include('leaves.urls')),
    path('payroll/', include('payroll.urls')),
    path('hr/', include('hr_modules.urls')),
    path('ai/', include('ai_engine.urls')),
    path('collab/', include('collab.urls')),
    path('soc/', include('soc.urls')),
    path('cron/soc/', soc_views.cron_scan, name='soc_cron_scan'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
