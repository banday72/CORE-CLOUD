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
]

# Root-level cron route is wired in hr_payroll/urls.py as /cron/soc/.
