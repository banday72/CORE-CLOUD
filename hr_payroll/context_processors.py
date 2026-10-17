def role_context(request):
    from employees.permissions import permissions_for_user, Perms, permission_group
    context = {
        'is_hr': False, 'current_employee': None, 'ceo_employee': None,
        'current_manager': None, 'unread_notif_count': 0,
        'permissions': set(), 'can': Perms(set()), 'permission_group': 'employee',
    }
    if request.user.is_authenticated:
        from django.core.cache import cache
        from employees.models import Employee

        context['ceo_employee'] = cache.get('cc_ceo_employee')
        if context['ceo_employee'] is None:
            try:
                context['ceo_employee'] = Employee.objects.get(employee_id='CEO001')
                cache.set('cc_ceo_employee', context['ceo_employee'], 300)
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
            from django.db.models import Count, Q, F
            from collab.models import ConversationMember
            if context.get('current_employee'):
                me = context['current_employee']
                if 'chat' in context.get('collab_blocked', set()):
                    context['collab_unread_chat'] = 0
                else:
                    rows = ConversationMember.objects.filter(employee=me).annotate(
                        n=Count('conversation__messages', filter=(
                            Q(conversation__messages__isnull=False)
                            & (Q(last_read_at__isnull=True)
                               | Q(conversation__messages__created_at__gt=F('last_read_at')))
                            & ~Q(conversation__messages__sender=me)
                        ))
                    )
                    context['collab_unread_chat'] = sum(r.n for r in rows)
        except Exception:
            pass
    return context


def login_slides(request):
    if request.user.is_authenticated:
        return {'login_slides': []}
    slides = []
    try:
        from employees.models import LoginSlide
        slides = [slide.picture_b64 for slide in LoginSlide.objects.filter(is_active=True)[:6]]
    except Exception:
        pass
    return {'login_slides': slides}
