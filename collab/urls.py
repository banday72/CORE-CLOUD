from django.urls import path

from . import views

urlpatterns = [
    path('mail/', views.mail_inbox, name='collab_mail'),
    path('mail/sent/', views.mail_sent, name='collab_mail_sent'),
    path('mail/compose/', views.mail_compose, name='collab_mail_compose'),
    path('mail/<int:pk>/', views.mail_detail, name='collab_mail_detail'),
    path('mail/<int:pk>/delete/', views.mail_delete, name='collab_mail_delete'),

    path('chat/', views.chat_home, name='collab_chat'),
    path('chat/<int:conv_id>/', views.chat_home, name='collab_chat_room'),
    path('chat/<int:conv_id>/send/', views.chat_send, name='collab_chat_send'),
    path('chat/<int:conv_id>/messages/', views.chat_messages_json, name='collab_chat_messages'),
    path('chat/start-direct/', views.chat_start_direct, name='collab_chat_start_direct'),
    path('chat/start-group/', views.chat_start_group, name='collab_chat_start_group'),

    path('meetings/', views.meeting_list, name='collab_meetings'),
    path('meetings/create/', views.meeting_create, name='collab_meeting_create'),
    path('meetings/<int:pk>/', views.meeting_detail, name='collab_meeting_detail'),
    path('meetings/<int:pk>/respond/', views.meeting_respond, name='collab_meeting_respond'),
]
