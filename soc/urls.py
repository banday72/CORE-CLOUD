from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='soc_dashboard'),
    path('events/', views.event_list, name='soc_event_list'),
    path('api/stats/', views.api_stats, name='soc_api_stats'),
    path('api/events/live/', views.api_live_events, name='soc_api_live'),
    path('alerts/', views.alert_list, name='soc_alert_list'),
    path('alerts/<int:pk>/', views.alert_detail, name='soc_alert_detail'),
    path('alerts/<int:pk>/action/', views.alert_action, name='soc_alert_action'),
    path('incidents/', views.incident_list, name='soc_incident_list'),
    path('incidents/<int:pk>/', views.incident_detail, name='soc_incident_detail'),
    path('incidents/<int:pk>/update/', views.incident_update, name='soc_incident_update'),
    path('rules/', views.rule_list, name='soc_rule_list'),
    path('rules/<int:pk>/toggle/', views.rule_toggle, name='soc_rule_toggle'),
    path('ip-list/', views.ip_list, name='soc_ip_list'),
    path('ip-list/add/', views.ip_add, name='soc_ip_add'),
    path('ip-list/<int:pk>/remove/', views.ip_remove, name='soc_ip_remove'),
    path('ip-list/users/add/', views.user_entry_add, name='soc_user_entry_add'),
    path('ip-list/users/<int:pk>/remove/', views.user_entry_remove, name='soc_user_entry_remove'),
]

# Root-level cron route is wired in hr_payroll/urls.py as /cron/soc/.
