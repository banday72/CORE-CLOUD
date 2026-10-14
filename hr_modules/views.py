from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from datetime import date, timedelta

from employees.decorators import permission_required
from employees.permissions import permissions_for_user
from .emails import send_ticket_email, email_team_members

def has_any_permission(user, *perms):
    return user.is_superuser or bool(perms and permissions_for_user(user) & set(perms))


def create_notification(employee, title, message, notif_type='info', link=''):
    from .models import Notification
    return Notification.objects.create(
        employee=employee, title=title, message=message,
        notif_type=notif_type, link=link
    )


# ============ ORG CHART ============
@login_required
def org_chart(request):
    from employees.models import Employee, is_chief_designation
    active = Employee.objects.filter(status='active')
    ceo = active.filter(employee_id='CEO001').first()
    if not ceo:
        ceo = active.filter(designation__icontains='chief executive').first()
    if not ceo:
        roots = [e for e in active if is_chief_designation(e.designation) and e.reports_to_id is None]
        ceo = roots[0] if roots else active.filter(reports_to__isnull=True).first()
    officers = Employee.objects.filter(reports_to=ceo, status='active') if ceo else []
    org_data = []
    for officer in officers:
        subs = Employee.objects.filter(reports_to=officer, status='active')
        org_data.append({'officer': officer, 'employees': list(subs)})
    return render(request, 'hr_modules/org_chart.html', {
        'ceo': ceo, 'org_data': org_data
    })


# ============ NOTIFICATIONS ============
@login_required
def notification_list(request):
    from employees.models import Employee
    from .models import Notification
    emp = Employee.objects.filter(user=request.user).first()
    if emp:
        notifs = Notification.objects.filter(employee=emp)
    elif request.user.is_superuser:
        notifs = Notification.objects.all()[:100]
    else:
        notifs = Notification.objects.none()
    return render(request, 'hr_modules/notification_list.html', {
        'notifications': notifs, 'unread_count': notifs.filter(is_read=False).count()
    })


@login_required
def notification_mark_read(request, pk):
    from .models import Notification
    notif = get_object_or_404(Notification, pk=pk)
    notif.is_read = True
    notif.save()
    if notif.link:
        return redirect(notif.link)
    return redirect('notification_list')


@login_required
def notification_mark_all_read(request):
    from employees.models import Employee
    from .models import Notification
    emp = Employee.objects.filter(user=request.user).first()
    if emp:
        Notification.objects.filter(employee=emp, is_read=False).update(is_read=True)
    return redirect('notification_list')


# ============ EMPLOYEE DOCUMENTS ============
@login_required
def document_list(request):
    from employees.models import Employee
    from .models import EmployeeDocument
    emp = Employee.objects.filter(user=request.user).first()
    if has_any_permission(request.user, 'manage_documents'):
        docs = EmployeeDocument.objects.all()
        emp_filter = request.GET.get('employee')
        if emp_filter:
            docs = docs.filter(employee__employee_id=emp_filter)
    elif emp:
        docs = EmployeeDocument.objects.filter(employee=emp)
    else:
        docs = EmployeeDocument.objects.none()
    return render(request, 'hr_modules/document_list.html', {'documents': docs})


@login_required
def document_upload(request):
    from employees.models import Employee
    from .models import EmployeeDocument
    emp = Employee.objects.filter(user=request.user).first()
    if request.method == 'POST':
        target_emp_id = request.POST.get('employee_id', emp.employee_id if emp else None)
        target_emp = Employee.objects.filter(employee_id=target_emp_id).first()
        if not target_emp:
            messages.error(request, 'Employee not found.')
            return redirect('document_list')
        if not (request.user.is_superuser or has_any_permission(request.user, 'manage_documents') or (emp and target_emp.pk == emp.pk)):
            messages.error(request, 'You can only upload documents for yourself.')
            return redirect('document_list')
        uploaded_file = request.FILES.get('file')
        if uploaded_file:
            import base64
            file_data = base64.b64encode(uploaded_file.read()).decode('utf-8')
            doc_type = request.POST.get('doc_type', 'other')
            title = request.POST.get('title', uploaded_file.name)
            EmployeeDocument.objects.create(
                employee=target_emp, doc_type=doc_type, title=title,
                file_data=file_data, file_name=uploaded_file.name,
                file_size=uploaded_file.size, notes=request.POST.get('notes', '')
            )
            messages.success(request, f'Document "{title}" uploaded successfully.')
            return redirect('document_list')
        else:
            messages.error(request, 'Please select a file.')
    return render(request, 'hr_modules/document_upload.html', {
        'employees': Employee.objects.filter(status='active')
    })


@login_required
def document_download(request, pk):
    import base64
    from django.http import HttpResponse
    from .models import EmployeeDocument
    doc = get_object_or_404(EmployeeDocument, pk=pk)
    file_bytes = base64.b64decode(doc.file_data)
    response = HttpResponse(file_bytes, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{doc.file_name}"'
    return response


@login_required
def document_delete(request, pk):
    from .models import EmployeeDocument
    doc = get_object_or_404(EmployeeDocument, pk=pk)
    if request.method == 'POST':
        doc.delete()
        messages.success(request, 'Document deleted.')
        return redirect('document_list')
    return render(request, 'hr_modules/document_confirm_delete.html', {'doc': doc})


# ============ PERFORMANCE REVIEWS ============
@login_required
def review_list(request):
    from employees.models import Employee
    from .models import PerformanceReview
    from django.db.models import Avg
    emp = Employee.objects.filter(user=request.user).first()
    period_filter = request.GET.get('period', '')
    year_filter = request.GET.get('year', '')
    employee_filter = request.GET.get('employee', '')

    if has_any_permission(request.user, 'manage_reviews'):
        reviews = PerformanceReview.objects.all()
    elif emp:
        reviews = PerformanceReview.objects.filter(employee=emp)
    else:
        reviews = PerformanceReview.objects.none()

    if period_filter:
        reviews = reviews.filter(period=period_filter)
    if year_filter:
        reviews = reviews.filter(year=int(year_filter))
    if employee_filter:
        reviews = reviews.filter(employee__employee_id=employee_filter)

    avg_rating = reviews.aggregate(avg=Avg('overall_rating'))['avg'] or 0
    total_reviews = reviews.count()
    completed = reviews.filter(status='completed').count()

    emp_stats = []
    if has_any_permission(request.user, 'manage_reviews'):
        all_emps = Employee.objects.filter(status='active')
        for e in all_emps:
            e_reviews = PerformanceReview.objects.filter(employee=e)
            e_avg = e_reviews.aggregate(avg=Avg('overall_rating'))['avg'] or 0
            e_count = e_reviews.count()
            emp_stats.append({'employee': e, 'avg_rating': e_avg, 'review_count': e_count})

    return render(request, 'hr_modules/review_list.html', {
        'reviews': reviews, 'avg_rating': round(float(avg_rating), 2),
        'total_reviews': total_reviews, 'completed': completed,
        'emp_stats': emp_stats, 'period_filter': period_filter,
        'year_filter': year_filter, 'employee_filter': employee_filter,
    })


@login_required
@permission_required('manage_reviews')
def review_create(request):
    from employees.models import Employee
    from .models import PerformanceReview
    if request.method == 'POST':
        emp_id = request.POST.get('employee_id')
        emp = get_object_or_404(Employee, employee_id=emp_id)
        reviewer = Employee.objects.filter(user=request.user).first()
        review = PerformanceReview.objects.create(
            employee=emp, reviewer=reviewer,
            period=request.POST.get('period'),
            year=int(request.POST.get('year', date.today().year)),
            technical_score=int(request.POST.get('technical_score', 3)),
            communication_score=int(request.POST.get('communication_score', 3)),
            teamwork_score=int(request.POST.get('teamwork_score', 3)),
            leadership_score=int(request.POST.get('leadership_score', 3)),
            initiative_score=int(request.POST.get('initiative_score', 3)),
            strengths=request.POST.get('strengths', ''),
            improvements=request.POST.get('improvements', ''),
            goals=request.POST.get('goals', ''),
            comments=request.POST.get('comments', ''),
            status='completed'
        )
        create_notification(emp, 'Performance Review',
            f'Your {review.get_period_display()} {review.year} review is ready. Rating: {review.overall_rating}/5',
            'info', 'review_list')
        messages.success(request, f'Review created for {emp.first_name} {emp.last_name}.')
        return redirect('review_list')
    return render(request, 'hr_modules/review_form.html', {
        'employees': Employee.objects.filter(status='active')
    })


@login_required
def review_detail(request, pk):
    from .models import PerformanceReview
    review = get_object_or_404(PerformanceReview, pk=pk)
    return render(request, 'hr_modules/review_detail.html', {'review': review})


# ============ TRAINING MODULE ============
@login_required
def training_list(request):
    from .models import Training
    trainings = Training.objects.all()
    return render(request, 'hr_modules/training_list.html', {'trainings': trainings})


@login_required
@permission_required('manage_training')
def training_create(request):
    from employees.models import Employee
    from .models import Training
    if request.method == 'POST':
        creator = Employee.objects.filter(user=request.user).first()
        training = Training.objects.create(
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            provider=request.POST.get('provider', ''),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date') or None,
            status=request.POST.get('status', 'planned'),
            created_by=creator
        )
        messages.success(request, f'Training "{training.title}" created.')
        return redirect('training_list')
    return render(request, 'hr_modules/training_form.html')


@login_required
@permission_required('manage_training')
def training_enroll(request, pk):
    from employees.models import Employee
    from .models import Training, TrainingEnrollment
    training = get_object_or_404(Training, pk=pk)
    if request.method == 'POST':
        emp_ids = request.POST.getlist('employees')
        count = 0
        for eid in emp_ids:
            emp = Employee.objects.filter(employee_id=eid).first()
            if emp:
                TrainingEnrollment.objects.get_or_create(training=training, employee=emp)
                create_notification(emp, 'Training Enrollment',
                    f'You have been enrolled in "{training.title}"', 'info', 'training_list')
                count += 1
        messages.success(request, f'{count} employees enrolled.')
        return redirect('training_list')
    return render(request, 'hr_modules/training_enroll.html', {
        'training': training,
        'employees': Employee.objects.filter(status='active')
    })


@login_required
def training_detail(request, pk):
    from .models import Training, TrainingEnrollment
    training = get_object_or_404(Training, pk=pk)
    enrollments = TrainingEnrollment.objects.filter(training=training)
    return render(request, 'hr_modules/training_detail.html', {
        'training': training, 'enrollments': enrollments
    })


# ============ TRAVEL & REIMBURSEMENT ============
@login_required
def travel_list(request):
    from employees.models import Employee
    from .models import TravelRequest
    emp = Employee.objects.filter(user=request.user).first()
    if has_any_permission(request.user, 'view_all_travel'):
        travels = TravelRequest.objects.all()
    elif emp:
        travels = TravelRequest.objects.filter(employee=emp)
    else:
        travels = TravelRequest.objects.none()
    status_filter = request.GET.get('status', '')
    if status_filter:
        travels = travels.filter(status=status_filter)
    return render(request, 'hr_modules/travel_list.html', {'travels': travels, 'status_filter': status_filter})


@login_required
def travel_create(request):
    from employees.models import Employee
    from .models import TravelRequest
    emp = Employee.objects.filter(user=request.user).first()
    if request.method == 'POST':
        import base64
        receipt = request.FILES.get('receipt')
        receipt_data = base64.b64encode(receipt.read()).decode('utf-8') if receipt else ''
        travel = TravelRequest.objects.create(
            employee=emp,
            destination=request.POST.get('destination'),
            purpose=request.POST.get('purpose'),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date'),
            estimated_cost=request.POST.get('estimated_cost', 0),
            receipt_data=receipt_data,
            notes=request.POST.get('notes', '')
        )
        if emp.reports_to:
            create_notification(emp.reports_to, 'Travel Request',
                f'{emp.first_name} {emp.last_name} requests travel to {travel.destination}',
                'warning', 'travel_list')
        messages.success(request, 'Travel request submitted.')
        return redirect('travel_list')
    return render(request, 'hr_modules/travel_form.html')


@login_required
@permission_required('approve_travel')
def travel_action(request, pk):
    from .models import TravelRequest
    travel = get_object_or_404(TravelRequest, pk=pk)
    if request.method == 'POST':
        from employees.models import Employee
        action = request.POST.get('action')
        reviewer = Employee.objects.filter(user=request.user).first()
        travel.status = action
        travel.approved_by = reviewer
        travel.save()
        create_notification(travel.employee, f'Travel {action.title()}',
            f'Your travel to {travel.destination} has been {action}.',
            'success' if action == 'approved' else 'danger', 'travel_list')
        messages.success(request, f'Travel request {action}.')
        return redirect('travel_list')
    return render(request, 'hr_modules/travel_action.html', {'travel': travel})


# ============ OVERTIME TRACKING ============
@login_required
def overtime_list(request):
    from employees.models import Employee
    from .models import OvertimeRecord
    emp = Employee.objects.filter(user=request.user).first()
    if has_any_permission(request.user, 'view_all_overtime'):
        records = OvertimeRecord.objects.all()
    elif emp:
        records = OvertimeRecord.objects.filter(employee=emp)
    else:
        records = OvertimeRecord.objects.none()
    status_filter = request.GET.get('status', '')
    if status_filter:
        records = records.filter(status=status_filter)
    return render(request, 'hr_modules/overtime_list.html', {'records': records, 'status_filter': status_filter})


@login_required
def overtime_create(request):
    from employees.models import Employee
    from .models import OvertimeRecord
    emp = Employee.objects.filter(user=request.user).first()
    if request.method == 'POST':
        ot = OvertimeRecord.objects.create(
            employee=emp,
            date=request.POST.get('date'),
            hours=request.POST.get('hours'),
            reason=request.POST.get('reason'),
            rate_multiplier=request.POST.get('rate_multiplier', 1.5)
        )
        if emp.reports_to:
            create_notification(emp.reports_to, 'Overtime Request',
                f'{emp.first_name} {emp.last_name} requests {ot.hours}h overtime on {ot.date}',
                'warning', 'overtime_list')
        messages.success(request, 'Overtime request submitted.')
        return redirect('overtime_list')
    return render(request, 'hr_modules/overtime_form.html')


@login_required
@permission_required('approve_overtime')
def overtime_action(request, pk):
    from .models import OvertimeRecord
    ot = get_object_or_404(OvertimeRecord, pk=pk)
    if request.method == 'POST':
        from employees.models import Employee
        action = request.POST.get('action')
        reviewer = Employee.objects.filter(user=request.user).first()
        ot.status = action
        ot.approved_by = reviewer
        ot.save()
        create_notification(ot.employee, f'Overtime {action.title()}',
            f'Your overtime on {ot.date} ({ot.hours}h) has been {action}.',
            'success' if action == 'approved' else 'danger', 'overtime_list')
        messages.success(request, f'Overtime {action}.')
        return redirect('overtime_list')
    return render(request, 'hr_modules/overtime_action.html', {'record': ot})


# ============ IT & NETWORKS HELP DESK ============
IT_TEAMS = ('networks', 'software', 'hardware')


def notify_team(team, title, message, notif_type='info', link='', email=True):
    from employees.models import Employee
    for emp in Employee.objects.filter(status='active', user__isnull=False, support_team=team):
        create_notification(emp, title, message, notif_type, link)
    if email:
        email_team_members(team, f'[IT Help Desk] {title}', message)


def resolvable_teams(user):
    return [t for t in IT_TEAMS if has_any_permission(user, 'resolve_' + t)]


@login_required
def networks_ticket_list(request):
    from employees.models import Employee
    from .models import NetworkTicket
    emp = Employee.objects.filter(user=request.user).first()
    tickets = NetworkTicket.objects.none()
    if emp:
        mine = NetworkTicket.objects.filter(employee=emp)
        teams = resolvable_teams(request.user)
        if teams:
            mine = mine | NetworkTicket.objects.filter(assigned_team__in=teams)
        if has_any_permission(request.user, 'manage_it_teams'):
            mine = NetworkTicket.objects.all()
        tickets = mine.distinct()
    status_filter = request.GET.get('status', '')
    team_filter = request.GET.get('team', '')
    assigned_me = request.GET.get('assigned') == 'me'
    overdue = request.GET.get('overdue') == '1'
    assigned_to_me_count = 0
    overdue_count = 0
    if emp:
        assigned_to_me_count = tickets.filter(assigned_to=emp).exclude(status__in=['resolved', 'rejected']).count()
        overdue_count = tickets.filter(sla_due_at__lt=timezone.now()).exclude(status__in=['resolved', 'rejected']).count()
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    if team_filter:
        tickets = tickets.filter(assigned_team=team_filter)
    if assigned_me and emp:
        tickets = tickets.filter(assigned_to=emp)
    if overdue:
        tickets = tickets.filter(sla_due_at__lt=timezone.now()).exclude(status__in=['resolved', 'rejected'])
    return render(request, 'hr_modules/networks_ticket_list.html', {
        'tickets': tickets, 'status_filter': status_filter, 'team_filter': team_filter,
        'is_resolver': bool(resolvable_teams(request.user)),
        'assigned_me': assigned_me,
        'assigned_to_me_count': assigned_to_me_count,
        'overdue': overdue,
        'overdue_count': overdue_count,
        'my_emp_id': emp.pk if emp else None,
    })


@login_required
def networks_ticket_create(request):
    from employees.models import Employee
    from .models import NetworkTicket
    emp = Employee.objects.filter(user=request.user).first()
    if request.method == 'POST':
        category = request.POST.get('category', 'networks')
        ticket = NetworkTicket.objects.create(
            employee=emp,
            category=category,
            assigned_team=NetworkTicket.team_for_category(category),
            priority=request.POST.get('priority', 'medium'),
            subject=request.POST.get('subject'),
            description=request.POST.get('description'),
            status='approved',
        )
        notify_team(ticket.assigned_team, 'IT/Network Ticket',
            f'New {ticket.get_assigned_team_display()} ticket "{ticket.subject}" from {emp} needs your attention.',
            'warning', 'networks_ticket_list')
        send_ticket_email(emp, f'[IT Help Desk] Ticket #{ticket.pk} received',
            f'Hi {emp.first_name},\n\nYour ticket "{ticket.subject}" has been received and routed to the '
            f'{ticket.get_assigned_team_display()} (Priority: {ticket.get_priority_display()}).\n'
            f'We will get back to you soon.\n\n- CoreCloud IT Help Desk')
        messages.success(request, 'Ticket submitted and routed to the IT team.')
        return redirect('networks_ticket_list')
    return render(request, 'hr_modules/networks_ticket_form.html')


@login_required
def networks_ticket_detail(request, pk):
    from .models import NetworkTicket, TicketReply
    from django.core.exceptions import PermissionDenied
    ticket = get_object_or_404(NetworkTicket, pk=pk)
    from employees.models import Employee
    emp = Employee.objects.filter(user=request.user).first()
    can_resolve = has_any_permission(request.user, 'resolve_' + ticket.assigned_team)
    can_manage_it = has_any_permission(request.user, 'manage_it_teams')
    can_handle = can_resolve or can_manage_it or request.user.is_superuser
    is_owner = bool(emp) and ticket.employee_id == emp.pk
    if not (can_handle or is_owner):
        raise PermissionDenied
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'reply':
            if not can_handle:
                raise PermissionDenied
            message = (request.POST.get('message') or '').strip()
            is_internal = request.POST.get('visibility') == 'internal'
            if message:
                TicketReply.objects.create(ticket=ticket, author=emp, team=ticket.assigned_team,
                                           message=message, is_internal=is_internal)
                if not is_internal:
                    if not ticket.first_response_at:
                        ticket.first_response_at = timezone.now()
                        ticket.save(update_fields=['first_response_at', 'updated_at'])
                    if ticket.employee_id != (emp.pk if emp else None):
                        create_notification(ticket.employee, 'Ticket Reply',
                            f'{ticket.get_assigned_team_display()} replied on your ticket "{ticket.subject}".',
                            'info', 'networks_ticket_list')
                        send_ticket_email(ticket.employee, f'[IT Help Desk] Reply on ticket #{ticket.pk}',
                            f'{ticket.get_assigned_team_display()} replied on your ticket "{ticket.subject}":\n\n{message}\n\n'
                            f'- CoreCloud IT Help Desk')
                messages.success(request, 'Internal note added.' if is_internal else 'Reply posted.')
            else:
                messages.warning(request, 'Reply cannot be empty.')
        elif action == 'assign':
            if not can_handle:
                raise PermissionDenied
            member_id = request.POST.get('member_id', '')
            team_members = Employee.objects.filter(status='active', support_team=ticket.assigned_team)
            member = team_members.filter(pk=member_id).first() if member_id else None
            ticket.assigned_to = member
            ticket.save(update_fields=['assigned_to', 'updated_at'])
            if member and member.pk != (emp.pk if emp else None):
                if member.user_id:
                    create_notification(member, 'Ticket Assigned',
                        f'Ticket "{ticket.subject}" ({ticket.get_assigned_team_display()}) has been assigned to you.',
                        'warning', 'networks_ticket_list')
                send_ticket_email(member, f'[IT Help Desk] Ticket #{ticket.pk} assigned to you',
                    f'You have been assigned ticket "{ticket.subject}" (Priority: {ticket.get_priority_display()}).\n'
                    f'Please review it in the IT Help Desk.\n\n- CoreCloud IT Help Desk')
            messages.success(request, 'Ticket assigned.' if member else 'Assignment cleared.')
        return redirect('networks_ticket_detail', pk=ticket.pk)
    team_members = Employee.objects.filter(status='active', support_team=ticket.assigned_team).order_by('first_name')
    replies = ticket.replies.select_related('author')
    if not can_handle:
        replies = replies.filter(is_internal=False)
    return render(request, 'hr_modules/networks_ticket_detail.html', {
        'ticket': ticket,
        'can_manage': can_handle,
        'can_reply': can_handle,
        'is_owner': is_owner,
        'emp': emp,
        'replies': replies,
        'team_members': team_members,
    })


@login_required
def networks_ticket_action(request, pk):
    from employees.models import Employee
    from .models import NetworkTicket
    from django.core.exceptions import PermissionDenied
    ticket = get_object_or_404(NetworkTicket, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        reviewer = Employee.objects.filter(user=request.user).first()
        if action in ('in_progress', 'resolved'):
            if not (has_any_permission(request.user, 'resolve_' + ticket.assigned_team)
                    or has_any_permission(request.user, 'manage_it_teams')
                    or request.user.is_superuser):
                raise PermissionDenied
            ticket.status = action
            if not ticket.first_response_at:
                ticket.first_response_at = timezone.now()
            ticket.resolved_by = reviewer if action == 'resolved' else ticket.resolved_by
            if action == 'resolved':
                ticket.resolution_notes = request.POST.get('resolution_notes', '')
                ticket.resolved_at = timezone.now()
            ticket.save()
            create_notification(ticket.employee, f'Ticket {action.title().replace("_", " ")}',
                f'Your ticket "{ticket.subject}" is now {action.replace("_", " ")}.'
                + (f' Notes: {ticket.resolution_notes}' if ticket.resolution_notes else ''),
                'success' if action == 'resolved' else 'info', 'networks_ticket_list')
            if action == 'resolved':
                send_ticket_email(ticket.employee, f'[IT Help Desk] Ticket #{ticket.pk} resolved',
                    f'Your ticket "{ticket.subject}" has been resolved.\n'
                    + (f'Notes: {ticket.resolution_notes}\n' if ticket.resolution_notes else '')
                    + '\nIf the issue persists, please reply in the IT Help Desk.\n\n- CoreCloud IT Help Desk')
            messages.success(request, f'Ticket marked {action.replace("_", " ")}.')
        return redirect('networks_ticket_list')
    return redirect('networks_ticket_detail', pk=ticket.pk)


# ============ IT TEAMS (password reset) ============
@login_required
def networks_reset_password(request):
    from employees.models import Employee, generate_temp_password, find_employee_by_id
    from employees.audit import log_audit
    from .models import NetworkTicket, TicketReply
    from django.core.cache import cache
    from django.core.exceptions import PermissionDenied

    if request.method != 'POST':
        return redirect('networks_ticket_list')

    if not has_any_permission(request.user, 'resolve_networks', 'manage_it_teams'):
        raise PermissionDenied

    employee_id = (request.POST.get('employee_id') or '').strip()
    emp = find_employee_by_id(employee_id)
    if emp is None:
        messages.error(request, f'No employee found with ID "{employee_id}".')
        return redirect('networks_ticket_list')
    if emp.user is None:
        messages.error(request, f'{emp.full_name} ({emp.employee_id}) has no login account to reset.')
        return redirect('networks_ticket_list')

    team_emp = Employee.objects.filter(user=request.user).first()
    temp_password = generate_temp_password()
    emp.user.set_password(temp_password)
    emp.user.save(update_fields=['password'])
    emp.must_change_password = True
    emp.failed_login_attempts = 0
    emp.save(update_fields=['must_change_password', 'failed_login_attempts'])
    cache.delete(f'login_attempts_user_{emp.employee_id}')
    cache.delete(f'login_attempts_{request.META.get("REMOTE_ADDR")}')

    log_audit(user=request.user, action='password_change', model_name='User',
              object_id=emp.employee_id,
              description=f'Password reset by IT/Networks team for {emp.full_name}',
              request=request)

    ticket_id = request.POST.get('ticket')
    if ticket_id:
        ticket = NetworkTicket.objects.filter(pk=ticket_id).first()
        if ticket:
            TicketReply.objects.create(
                ticket=ticket, author=team_emp, team=ticket.assigned_team,
                message=f'Password reset performed by {team_emp.full_name if team_emp else "IT team"}. '
                        f'A temporary password was issued and shared securely with the employee.',
                is_internal=True,
            )
            if not ticket.first_response_at:
                ticket.first_response_at = timezone.now()
                ticket.save(update_fields=['first_response_at', 'updated_at'])

    messages.success(
        request,
        f'Password reset for {emp.full_name} ({emp.employee_id}). '
        f'Temporary password: {temp_password} — share it securely; '
        f'the employee must change it on next login.'
    )
    if ticket_id:
        return redirect('networks_ticket_detail', pk=ticket_id)
    return redirect('networks_ticket_list')


# ============ IT TEAMS (assignment) ============
@login_required
@permission_required('manage_it_teams')
def network_teams(request):
    from employees.models import Employee
    from django.db.models import Q
    search = request.GET.get('search', '')
    team_filter = request.GET.get('team', '')
    employees = Employee.objects.filter(status='active').select_related('department').order_by('first_name', 'last_name')
    if search:
        employees = employees.filter(
            Q(employee_id__icontains=search) | Q(first_name__icontains=search) |
            Q(last_name__icontains=search) | Q(designation__icontains=search))
    if team_filter == 'none':
        employees = employees.filter(support_team='')
    elif team_filter:
        employees = employees.filter(support_team=team_filter)
    else:
        employees = employees.filter(support_team__in=['networks', 'software', 'hardware'])
    if request.method == 'POST':
        upload = request.FILES.get('csv_file')
        if upload:
            import csv, io
            valid = {
                'networks': 'networks', 'software': 'software', 'hardware': 'hardware',
                'networks team': 'networks', 'software team': 'software', 'hardware team': 'hardware',
                '': '', 'none': '', '-': '',
            }
            raw_bytes = upload.read()
            try:
                text = raw_bytes.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw_bytes.decode('latin-1')
            updated, skipped, errors = 0, 0, []
            for i, row in enumerate(csv.reader(io.StringIO(text)), start=1):
                if not row or not row[0].strip():
                    continue
                if i == 1 and row[0].strip().lower() in ('employee_id', 'employee id', 'id'):
                    continue
                emp_id = row[0].strip()
                raw = row[1].strip().lower() if len(row) > 1 else ''
                if raw not in valid:
                    errors.append(f'row {i}: invalid team "{raw}" for {emp_id}')
                    skipped += 1
                    continue
                emp = Employee.objects.filter(employee_id__iexact=emp_id).first()
                if not emp:
                    errors.append(f'row {i}: employee {emp_id} not found')
                    skipped += 1
                    continue
                team = valid[raw]
                if emp.support_team != team:
                    emp.support_team = team
                    emp.save(update_fields=['support_team'])
                    updated += 1
            msg = f'CSV imported: {updated} updated, {skipped} skipped.'
            if errors:
                messages.warning(request, msg + ' Issues: ' + '; '.join(errors[:5]) + (' ...' if len(errors) > 5 else ''))
            else:
                messages.success(request, msg)
            return redirect('network_teams')
        changed = 0
        for emp in Employee.objects.filter(status='active'):
            fields = []
            key = 'team_%s' % emp.pk
            if key in request.POST:
                val = request.POST.get(key, '')
                if val in ('', 'networks', 'software', 'hardware') and emp.support_team != val:
                    emp.support_team = val
                    fields.append('support_team')
            rkey = 'role_%s' % emp.pk
            if rkey in request.POST:
                val = request.POST.get(rkey, '')
                if val in ('', 'manager', 'assistant_manager') and emp.it_role != val:
                    emp.it_role = val
                    fields.append('it_role')
            mkey = 'itmgr_%s' % emp.pk
            if mkey in request.POST:
                is_mgr = request.POST.get(mkey) == 'on'
                if emp.is_it_manager != is_mgr:
                    emp.is_it_manager = is_mgr
                    fields.append('is_it_manager')
            if fields:
                emp.save(update_fields=fields)
                changed += 1
        messages.success(request, f'IT team settings updated ({changed} change(s)).')
        return redirect('network_teams')
    return render(request, 'hr_modules/network_teams.html', {
        'employees': employees, 'search': search, 'team_filter': team_filter,
        'team_choices': Employee.SUPPORT_TEAM_CHOICES,
        'it_role_choices': Employee.IT_ROLE_CHOICES,
    })


# ============ IT HELP DESK ANALYTICS ============
@login_required
@permission_required('manage_it_teams')
def network_analytics(request):
    from employees.models import Employee
    from .models import NetworkTicket
    from django.db.models import Q, Count, Avg, F, ExpressionWrapper, DurationField
    now = timezone.now()
    all_tickets = NetworkTicket.objects.all()
    totals = {
        'total': all_tickets.count(),
        'open': all_tickets.filter(status__in=['pending', 'approved']).count(),
        'in_progress': all_tickets.filter(status='in_progress').count(),
        'resolved': all_tickets.filter(status='resolved').count(),
        'overdue': all_tickets.filter(sla_due_at__lt=now).exclude(status__in=['resolved', 'rejected']).count(),
    }

    teams = []
    for value, label in NetworkTicket.TEAM_CHOICES:
        qs = all_tickets.filter(assigned_team=value)
        resolved = qs.filter(resolved_at__isnull=False)
        res = resolved.annotate(
            dur=ExpressionWrapper(F('resolved_at') - F('created_at'), output_field=DurationField())
        ).aggregate(avg=Avg('dur'))['avg']
        avg_hours = round(res.total_seconds() / 3600, 1) if res else None
        teams.append({
            'label': label, 'value': value,
            'open': qs.exclude(status__in=['resolved', 'rejected']).count(),
            'resolved': resolved.count(),
            'overdue': qs.filter(sla_due_at__lt=now).exclude(status__in=['resolved', 'rejected']).count(),
            'avg_hours': avg_hours,
        })

    members = (Employee.objects.filter(status='active', support_team__in=['networks', 'software', 'hardware'])
               .annotate(open_load=Count('network_tickets_assigned',
                                         filter=~Q(network_tickets_assigned__status__in=['resolved', 'rejected'])))
               .order_by('-open_load', 'first_name'))

    categories = (all_tickets.values('category').annotate(c=Count('id')).order_by('-c'))
    cat_map = dict(NetworkTicket.CATEGORY_CHOICES)
    categories = [{'label': cat_map.get(c['category'], c['category']), 'count': c['c']} for c in categories]

    return render(request, 'hr_modules/network_analytics.html', {
        'totals': totals, 'teams': teams, 'members': members,
        'categories': categories, 'max_cat': max([c['count'] for c in categories], default=1),
    })


# ============ ANNOUNCEMENTS / NOTICE BOARD ============
def active_announcements():
    from django.db.models import Q
    from datetime import date
    from .models import Announcement
    today = date.today()
    return Announcement.objects.filter(
        Q(publish_from__isnull=True) | Q(publish_from__lte=today),
        Q(publish_until__isnull=True) | Q(publish_until__gte=today),
    )


def broadcast_announcement(ann):
    from employees.models import Employee
    notif_type = 'danger' if ann.priority == 'urgent' else 'warning'
    for emp in Employee.objects.filter(status='active', user__isnull=False):
        create_notification(emp, f'Announcement: {ann.title}',
            ann.body[:160], notif_type, 'announcement_list')


@login_required
def announcement_list(request):
    from .models import Announcement
    can_manage = has_any_permission(request.user, 'manage_announcements')
    announcements = Announcement.objects.all() if can_manage else active_announcements()
    return render(request, 'hr_modules/announcement_list.html', {
        'announcements': announcements, 'can_manage': can_manage,
    })


@login_required
@permission_required('manage_announcements')
def announcement_create(request):
    from employees.models import Employee
    from .models import Announcement
    if request.method == 'POST':
        import base64
        poster = Employee.objects.filter(user=request.user).first()
        attachment = request.FILES.get('attachment')
        attachment_b64 = ''
        attachment_name = ''
        if attachment:
            attachment_b64 = 'data:%s;base64,%s' % (
                attachment.content_type or 'application/octet-stream',
                base64.b64encode(attachment.read()).decode('utf-8'))
            attachment_name = attachment.name
        ann = Announcement.objects.create(
            title=request.POST.get('title'),
            body=request.POST.get('body'),
            priority=request.POST.get('priority', 'normal'),
            is_pinned=request.POST.get('is_pinned') == 'on',
            publish_from=request.POST.get('publish_from') or None,
            publish_until=request.POST.get('publish_until') or None,
            posted_by=poster,
            attachment_b64=attachment_b64,
            attachment_name=attachment_name,
        )
        broadcast_announcement(ann)
        messages.success(request, 'Announcement published.')
        return redirect('announcement_list')
    return render(request, 'hr_modules/announcement_form.html', {'announcement': None})


@login_required
@permission_required('manage_announcements')
def announcement_edit(request, pk):
    from .models import Announcement
    ann = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        ann.title = request.POST.get('title')
        ann.body = request.POST.get('body')
        ann.priority = request.POST.get('priority', 'normal')
        ann.is_pinned = request.POST.get('is_pinned') == 'on'
        ann.publish_from = request.POST.get('publish_from') or None
        ann.publish_until = request.POST.get('publish_until') or None
        ann.save()
        messages.success(request, 'Announcement updated.')
        return redirect('announcement_list')
    return render(request, 'hr_modules/announcement_form.html', {'announcement': ann})


@login_required
@permission_required('manage_announcements')
def announcement_delete(request, pk):
    from .models import Announcement
    ann = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        ann.delete()
        messages.success(request, 'Announcement deleted.')
    return redirect('announcement_list')
