def role_context(request):
    from employees.permissions import permissions_for_user, Perms, permission_group
    context = {
        'is_hr': False, 'current_employee': None, 'ceo_employee': None,
        'current_manager': None, 'unread_notif_count': 0,
        'permissions': set(), 'can': Perms(set()), 'permission_group': 'employee',
    }
    if request.user.is_authenticated:
        from employees.models import Employee

        try:
            ceo = Employee.objects.get(employee_id='CEO001')
            context['ceo_employee'] = ceo
        except Exception:
            pass

        try:
            perms = permissions_for_user(request.user)
            context['permissions'] = perms
            context['can'] = Perms(perms)
            context['permission_group'] = permission_group(request.user.employee)
            emp = context['current_employee'] = request.user.employee
            context['is_hr'] = bool(perms & {'dashboard_hr', 'view_employees', 'manage_employees'})
            if emp.reports_to:
                context['current_manager'] = emp.reports_to
        except Employee.DoesNotExist:
            if request.user.is_superuser:
                context['is_hr'] = True
                context['permission_group'] = 'superuser'
                context['permissions'] = permissions_for_user(request.user)
                context['can'] = Perms(context['permissions'])

        try:
            from hr_modules.models import Notification
            if context.get('current_employee'):
                context['unread_notif_count'] = Notification.objects.filter(employee=context['current_employee'], is_read=False).count()
            elif request.user.is_superuser:
                context['unread_notif_count'] = Notification.objects.filter(is_read=False).count()
        except Exception:
            pass

        try:
            from collab.access import blocked_features
            if context.get('current_employee'):
                context['collab_blocked'] = blocked_features(context['current_employee'])
            else:
                context['collab_blocked'] = set()
        except Exception:
            context['collab_blocked'] = set()

        try:
            from collab.models import MailRecipient
            if context.get('current_employee'):
                if 'mail' in context.get('collab_blocked', set()):
                    context['collab_unread_mail'] = 0
                else:
                    context['collab_unread_mail'] = MailRecipient.objects.filter(
                        employee=context['current_employee'], is_read=False, is_deleted=False).count()
        except Exception:
            pass

        try:
            from collab.models import Conversation, ConversationMember
            if context.get('current_employee'):
                me = context['current_employee']
                if 'chat' in context.get('collab_blocked', set()):
                    context['collab_unread_chat'] = 0
                else:
                    total = 0
                    for membership in ConversationMember.objects.filter(employee=me).select_related('conversation'):
                        unread = membership.conversation.messages.exclude(sender=me)
                        if membership.last_read_at:
                            unread = unread.filter(created_at__gt=membership.last_read_at)
                        total += unread.count()
                    context['collab_unread_chat'] = total
        except Exception:
            pass
    return context


def login_slides(request):
    slides = []
    try:
        from employees.models import LoginSlide
        slides = [slide.picture_b64 for slide in LoginSlide.objects.filter(is_active=True)[:6]]
    except Exception:
        pass
    return {'login_slides': slides}
