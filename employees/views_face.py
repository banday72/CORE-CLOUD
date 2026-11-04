import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from employees.models import Employee, Department
from employees.decorators import permission_required


@login_required
def face_register(request):
    employee = None
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        pass
    if request.user.is_superuser and not employee:
        return render(request, 'face/face_register.html', {'employee': None, 'is_superuser': True})
    return render(request, 'face/face_register.html', {'employee': employee, 'is_superuser': False})


@csrf_exempt
def face_save(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            face_descriptors = data.get('descriptors', [])
            employee = Employee.objects.get(user=request.user)
            employee.face_data = json.dumps(face_descriptors)
            employee.face_registered = True
            employee.save()
            return JsonResponse({'status': 'ok', 'message': 'Face registered successfully'})
        except Employee.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'No employee profile linked to your account'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)


@login_required
def face_verify_page(request):
    employee = None
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        pass
    return render(request, 'face/face_verify.html', {'employee': employee})


@csrf_exempt
def face_verify(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            face_descriptors = data.get('descriptors', [])
            employee = Employee.objects.get(user=request.user)

            if not employee.face_registered or not employee.face_data:
                return JsonResponse({'status': 'ok', 'message': 'No face registered - skipping verification'})

            stored = json.loads(employee.face_data)
            if not stored:
                return JsonResponse({'status': 'ok', 'message': 'No face data stored - skipping verification'})

            for stored_desc in stored:
                for input_desc in face_descriptors:
                    if len(stored_desc) == len(input_desc):
                        distance = sum((a - b) ** 2 for a, b in zip(stored_desc, input_desc)) ** 0.5
                        if distance < 0.4:
                            return JsonResponse({'status': 'ok', 'message': 'Face verified'})

            return JsonResponse({'status': 'error', 'message': 'Face does not match'})
        except Employee.DoesNotExist:
            return JsonResponse({'status': 'ok', 'message': 'No employee profile - skipping verification'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)


@login_required
@permission_required('manage_faces')
def face_manage_list(request):
    employees = Employee.objects.filter(status='active').select_related('department', 'user').order_by('employee_id')
    search = request.GET.get('search', '')
    dept_id = request.GET.get('department', '')
    face_filter = request.GET.get('face_status', '')

    if search:
        employees = employees.filter(employee_id__icontains=search) | employees.filter(first_name__icontains=search) | employees.filter(last_name__icontains=search)
    if dept_id:
        employees = employees.filter(department_id=dept_id)
    if face_filter == 'registered':
        employees = employees.filter(face_registered=True)
    elif face_filter == 'not_registered':
        employees = employees.filter(face_registered=False)

    departments = Department.objects.all()
    return render(request, 'face/face_manage.html', {
        'employees': employees,
        'departments': departments,
        'search': search,
        'selected_dept': dept_id,
        'face_filter': face_filter,
    })


@csrf_exempt
def face_save_for_employee(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            emp_id = data.get('employee_id')
            face_descriptors = data.get('descriptors', [])
            employee = Employee.objects.get(employee_id=emp_id)
            if not request.user.is_superuser:
                from .permissions import permissions_for_user
                if 'manage_faces' not in permissions_for_user(request.user):
                    return JsonResponse({'status': 'error', 'message': 'Access denied.'}, status=403)
            employee.face_data = json.dumps(face_descriptors)
            employee.face_registered = True
            employee.save()
            return JsonResponse({'status': 'ok', 'message': f'Face registered for {employee.full_name}'})
        except Employee.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Employee not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)


@csrf_exempt
def face_remove_for_employee(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            emp_id = data.get('employee_id')
            employee = Employee.objects.get(employee_id=emp_id)
            if not request.user.is_superuser:
                from .permissions import permissions_for_user
                if 'manage_faces' not in permissions_for_user(request.user):
                    return JsonResponse({'status': 'error', 'message': 'Access denied.'}, status=403)
            employee.face_data = ''
            employee.face_registered = False
            employee.save()
            return JsonResponse({'status': 'ok', 'message': f'Face removed for {employee.full_name}'})
        except Employee.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Employee not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)
