import json
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from employees.models import Employee


def face_login_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'face/face_login.html')


@csrf_exempt
def face_login_check(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            face_descriptors = data.get('descriptors', [])

            employees = Employee.objects.filter(
                face_registered=True,
                face_data__isnull=False,
                status='active',
                user__isnull=False,
            ).exclude(face_data='').select_related('user')

            best_match = None
            best_distance = 1.0

            for emp in employees:
                try:
                    stored = json.loads(emp.face_data)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not stored:
                    continue

                for stored_desc in stored:
                    for input_desc in face_descriptors:
                        if len(stored_desc) == len(input_desc):
                            distance = sum((a - b) ** 2 for a, b in zip(stored_desc, input_desc)) ** 0.5
                            if distance < 0.4 and distance < best_distance:
                                best_distance = distance
                                best_match = emp

            if best_match and best_match.user:
                from soc.models import user_is_blacklisted
                if user_is_blacklisted(best_match.user.username):
                    from employees.audit import log_audit
                    log_audit(
                        user=best_match.user, action='login_failed',
                        model_name='Employee', object_id=best_match.employee_id,
                        description='Face login attempt on SOC-blacklisted account',
                        request=request, category='auth', outcome='failure',
                        severity='high',
                    )
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Your account has been disabled by IT & Networks. '
                                   'Please contact the IT Help Desk.',
                    })
                if best_match.is_login_locked:
                    from employees.lockout import locked_message
                    from employees.audit import log_audit
                    log_audit(
                        user=best_match.user, action='login_failed',
                        model_name='Employee', object_id=best_match.employee_id,
                        description='Face login attempt while account is locked',
                        request=request, category='auth', outcome='failure',
                        severity='medium',
                    )
                    return JsonResponse({'status': 'error', 'message': locked_message(best_match)})
                login(request, best_match.user, backend='hr_payroll.backends.AuthorizedUserBackend')
                from employees.audit import log_audit
                log_audit(
                    user=best_match.user, action='face_login',
                    model_name='Employee', object_id=best_match.employee_id,
                    description=f'Face login for {best_match.full_name} (match distance {best_distance:.3f})',
                    request=request, category='auth', outcome='success', severity='medium',
                )
                return JsonResponse({
                    'status': 'ok',
                    'message': f'Welcome {best_match.full_name}',
                    'employee_id': best_match.employee_id,
                    'redirect': '/'
                })

            from employees.audit import log_audit
            log_audit(
                user=None, action='face_login',
                model_name='Employee', object_id='',
                description='Face login failed — no matching face',
                request=request, category='auth', outcome='failure', severity='low',
            )
            return JsonResponse({'status': 'error', 'message': 'No matching face found. Try again or use password login.'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)
