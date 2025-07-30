from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for custom User model."""

    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_verified",
        "created_at",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "is_verified", "created_at")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-created_at",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {"fields": ("last_login", "date_joined", "created_at", "updated_at")},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin configuration for UserProfile model."""

    list_display = (
        "user",
        "current_title",
        "experience_level",
        "remote_ok",
        "location",
    )
    list_filter = ("experience_level", "remote_ok", "auto_apply_enabled")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "current_title",
        "current_company",
        "location",
    )
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "user",
                    "phone",
                    "location",
                    "linkedin_url",
                    "github_url",
                    "portfolio_url",
                )
            },
        ),
        (
            "Professional Information",
            {
                "fields": (
                    "current_title",
                    "current_company",
                    "experience_level",
                    "skills",
                    "industries",
                )
            },
        ),
        (
            "Job Search Preferences",
            {
                "fields": (
                    "preferred_locations",
                    "job_types",
                    "salary_min",
                    "salary_max",
                    "remote_ok",
                )
            },
        ),
        ("Documents", {"fields": ("resume", "cover_letter_template")}),
        (
            "AI & Automation",
            {
                "fields": (
                    "auto_apply_enabled",
                    "auto_apply_limit_daily",
                    "match_threshold",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    readonly_fields = ("created_at", "updated_at")
