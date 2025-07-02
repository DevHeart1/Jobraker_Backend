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
    list_display = ('id', 'session_id_display', 'role', 'message_preview', 'timestamp')
    list_filter = ('role', 'timestamp', 'session__user') # Allow filtering by user of the session
    search_fields = ('content', 'session__id', 'session__user__username')
    readonly_fields = ('timestamp',)
    list_select_related = ('session', 'session__user') # Optimize queries for list display

    fieldsets = (
        (None, {
            'fields': ('session', 'role', 'content')
        }),
        ('Function Call Data', {
            'fields': ('function_call_data', 'function_name'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('metadata', 'timestamp'),
            'classes': ('collapse',),
        }),
    )

    def session_id_display(self, obj):
        return str(obj.session.id)[:8] + "..."
    session_id_display.short_description = "Session ID"
    session_id_display.admin_order_field = 'session__id'

    def message_preview(self, obj):
        return (obj.content[:50] + '...') if len(obj.content) > 50 else obj.content
    message_preview.short_description = 'Message Preview'
