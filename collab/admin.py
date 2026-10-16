from django.contrib import admin

from .models import (
    Conversation, ConversationMember, ChatMessage,
    MailMessage, MailRecipient, MailSettings, Meeting, MeetingAttendee,
    CollabAccess,
)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'kind', 'title', 'created_by', 'updated_at')
    list_filter = ('kind',)


@admin.register(ConversationMember)
class ConversationMemberAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'employee', 'last_read_at')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'sender', 'created_at')
    list_filter = ('created_at',)


class MailRecipientInline(admin.TabularInline):
    model = MailRecipient
    extra = 0


@admin.register(MailMessage)
class MailMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'sender', 'mail_type', 'created_at')
    list_filter = ('mail_type',)
    inlines = [MailRecipientInline]


@admin.register(MailSettings)
class MailSettingsAdmin(admin.ModelAdmin):
    list_display = ('include_quote_in_reply', 'use_signature', 'default_mail_type', 'forward_style')

    def has_add_permission(self, request):
        return not MailSettings.objects.exists()


@admin.register(MailRecipient)
class MailRecipientAdmin(admin.ModelAdmin):
    list_display = ('mail', 'employee', 'kind', 'is_read', 'is_deleted')
    list_filter = ('kind', 'is_read', 'is_deleted')


class MeetingAttendeeInline(admin.TabularInline):
    model = MeetingAttendee
    extra = 0


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'organizer', 'start_at', 'end_at', 'status')
    list_filter = ('status',)
    inlines = [MeetingAttendeeInline]


@admin.register(MeetingAttendee)
class MeetingAttendeeAdmin(admin.ModelAdmin):
    list_display = ('meeting', 'employee', 'status')
    list_filter = ('status',)


@admin.register(CollabAccess)
class CollabAccessAdmin(admin.ModelAdmin):
    list_display = ('employee', 'block_mail', 'block_chat', 'block_meetings',
                    'blocked_by', 'updated_at')
    list_filter = ('block_mail', 'block_chat', 'block_meetings')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')
    raw_id_fields = ('employee', 'blocked_by')
