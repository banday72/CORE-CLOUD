from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from employees.decorators import permission_required
from .analytics import (
    attendance_analytics, payroll_anomaly_detection,
    employee_risk_prediction, salary_recommendations,
    natural_language_report, chatbot_response
)


@login_required
def ai_chatbot(request):
    response = None
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        if message:
            response = chatbot_response(message, request.user)
    return render(request, 'ai/chatbot.html', {'response': response})


@login_required
@permission_required('ai_analytics')
def ai_attendance_analytics(request):
    month = int(request.GET.get('month', 0))
    year = int(request.GET.get('year', 0))
    data = attendance_analytics(month or None, year or None)
    return render(request, 'ai/attendance_analytics.html', data)


@login_required
@permission_required('ai_analytics')
def ai_payroll_anomaly(request):
    data = payroll_anomaly_detection()
    return render(request, 'ai/payroll_anomaly.html', data)


@login_required
@permission_required('ai_analytics')
def ai_employee_risk(request):
    data = employee_risk_prediction()
    return render(request, 'ai/employee_risk.html', data)


@login_required
@permission_required('ai_analytics')
def ai_salary_recommendations(request):
    data = salary_recommendations()
    return render(request, 'ai/salary_recommendations.html', data)


@login_required
@permission_required('ai_analytics')
def ai_natural_report(request):
    result = None
    if request.method == 'POST':
        query = request.POST.get('query', '').strip()
        if query:
            result = natural_language_report(query)
    return render(request, 'ai/natural_report.html', {'result': result})
