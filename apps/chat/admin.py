from django.contrib import admin
from .models import ChatSession, ChatMessage

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'created_at', 'updated_at')
    list_filter = ('user', 'created_at', 'updated_at')
    search_fields = ('title', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('user', 'title')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',) # Keep timestamps collapsible
        }),
    )

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'session_id_display', 'sender', 'message_preview', 'created_at')
    list_filter = ('sender', 'created_at', 'session__user') # Allow filtering by user of the session
    search_fields = ('message_text', 'session__id', 'session__user__username')
    readonly_fields = ('created_at',)
    list_select_related = ('session', 'session__user') # Optimize queries for list display

    fieldsets = (
        (None, {
            'fields': ('session', 'sender', 'message_text')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def session_id_display(self, obj):
        return obj.session.id
    session_id_display.short_description = "Session ID"
    session_id_display.admin_order_field = 'session__id'


    def message_preview(self, obj):
        return (obj.message_text[:50] + '...') if len(obj.message_text) > 50 else obj.message_text
    message_preview.short_description = 'Message Preview'
