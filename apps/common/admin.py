from django.contrib import admin

from .models import KnowledgeArticle, VectorDocument


@admin.register(VectorDocument)
class VectorDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_type",
        "source_id",
        "text_content_preview",
        "created_at",
        "updated_at",
    )
    list_filter = ("source_type", "created_at")
    search_fields = ("source_id", "text_content", "metadata")
    readonly_fields = (
        "created_at",
        "updated_at",
        "embedding",
    )  # Embedding is too large to display well

    def text_content_preview(self, obj):
        return (
            (obj.text_content[:75] + "...")
            if len(obj.text_content) > 75
            else obj.text_content
        )

    text_content_preview.short_description = "Content Preview"


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "source_type", "category", "is_active", "updated_at")
    list_filter = ("source_type", "is_active", "category", "updated_at")
    search_fields = ("title", "content", "tags", "category")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "slug", "source_type", "category", "tags")}),
        ("Content", {"fields": ("content",)}),
        ("Status", {"fields": ("is_active",)}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),  # Collapsible section
            },
        ),
    )

    def get_queryset(self, request):
        # Optimize query if needed, e.g., prefetch_related for tags if it were a ManyToMany
        return super().get_queryset(request)


# If you have other models in 'common' app, register them here as well.
# For example, if you create a Tag model for KnowledgeArticle tags:
# from .models import Tag
# @admin.register(Tag)
# class TagAdmin(admin.ModelAdmin):
#     list_display = ('name', 'slug')
#     prepopulated_fields = {'slug': ('name',)}
