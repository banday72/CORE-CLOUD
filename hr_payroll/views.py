from django.shortcuts import redirect, render


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def terms(request):
    return render(request, 'legal/terms.html')


def privacy(request):
    return render(request, 'legal/privacy.html')
