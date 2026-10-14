from django.contrib import admin

from .models import (
    Conversation, ConversationMember, ChatMessage,
    MailMessage, MailRecipient, Meeting, MeetingAttendee,
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
    list_display = ('id', 'subject', 'sender', 'created_at')
    inlines = [MailRecipientInline]


@admin.register(MailRecipient)
class MailRecipientAdmin(admin.ModelAdmin):
    list_display = ('mail', 'employee', 'is_read', 'is_deleted')
    list_filter = ('is_read', 'is_deleted')


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
