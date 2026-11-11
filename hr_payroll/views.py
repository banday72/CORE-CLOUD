from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html', {
        'company_name': settings.COMPANY_NAME,
        'support_email': settings.SUPPORT_EMAIL,
        'status_url': settings.STATUS_URL,
    })


def terms(request):
    return render(request, 'legal/terms.html')


def privacy(request):
    return render(request, 'legal/privacy.html')


def pricing(request):
    return render(request, 'marketing/pricing.html')


def payroll_methodology(request):
    return render(request, 'marketing/payroll_methodology.html')


def onboarding(request):
    return render(request, 'marketing/onboarding.html')


def demo(request):
    return render(request, 'marketing/demo.html', {
        'demo_enabled': settings.DEMO_MODE,
        'demo_employee_id': settings.DEMO_EMPLOYEE_ID,
    })


@require_POST
def demo_login(request):
    if not settings.DEMO_MODE:
        return HttpResponse('The live demo is not enabled.', status=503)

    user = User.objects.filter(
        username=settings.DEMO_EMPLOYEE_ID,
        employee__is_authorized=True,
        is_active=True,
    ).select_related('employee').first()
    if user is None:
        return HttpResponse(
            'The live demo account is not configured. Set SEED_DEMO=True and run the demo setup.',
            status=503,
        )

    login(request, user, backend='hr_payroll.backends.AuthorizedUserBackend')
    return redirect('dashboard')
