from django.contrib import admin

from .models import (Alert, DetectionRule, Incident, IncidentNote, ResponseAction,
                     SOCIPEntry, SOCUserEntry)


@admin.register(DetectionRule)
class DetectionRuleAdmin(admin.ModelAdmin):
    list_display = ('key', 'name', 'severity', 'window_minutes', 'threshold', 'enabled', 'auto_response')
    list_filter = ('enabled', 'severity', 'auto_response')
    search_fields = ('key', 'name')


@admin.register(SOCIPEntry)
class SOCIPEntryAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'list_type', 'reason', 'added_by', 'created_at')
    list_filter = ('list_type',)
    search_fields = ('ip_address', 'reason')


@admin.register(SOCUserEntry)
class SOCUserEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'list_type', 'reason', 'added_by', 'created_at')
    list_filter = ('list_type',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'reason')
    raw_id_fields = ('user',)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('title', 'severity', 'status', 'count', 'subject_username', 'last_seen')
    list_filter = ('status', 'severity', 'rule')
    search_fields = ('title', 'fingerprint', 'subject_username')
    raw_id_fields = ('rule', 'event', 'incident', 'assignee')


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'severity', 'status', 'team', 'assignee', 'created_at')
    list_filter = ('status', 'severity', 'team')
    search_fields = ('title',)
    raw_id_fields = ('assignee',)


@admin.register(IncidentNote)
class IncidentNoteAdmin(admin.ModelAdmin):
    list_display = ('incident', 'author', 'kind', 'created_at')
    raw_id_fields = ('incident', 'author')


@admin.register(ResponseAction)
class ResponseActionAdmin(admin.ModelAdmin):
    list_display = ('action', 'actor', 'success', 'created_at')
    list_filter = ('action', 'success')
    raw_id_fields = ('alert', 'incident')
