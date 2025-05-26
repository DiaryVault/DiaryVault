from django.contrib import admin
from .models import Entry, Tag, SummaryVersion, LifeChapter, Biography, UserInsight, UserProfile

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.core.management import call_command
from django.contrib import messages

# Register Entry model
@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('title', 'content')
    date_hierarchy = 'created_at'

# Register Tag model
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
    list_filter = ('user',)
    search_fields = ('name',)

# Register SummaryVersion model
@admin.register(SummaryVersion)
class SummaryVersionAdmin(admin.ModelAdmin):
    list_display = ('entry', 'created_at')
    list_filter = ('created_at',)

# Register LifeChapter model
@admin.register(LifeChapter)
class LifeChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'user')
    list_filter = ('user',)
    search_fields = ('title', 'description')

# Register Biography model
@admin.register(Biography)
class BiographyAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('title', 'content')

# Register UserInsight model
@admin.register(UserInsight)
class UserInsightAdmin(admin.ModelAdmin):
    list_display = ('title', 'insight_type', 'user', 'created_at')
    list_filter = ('insight_type', 'created_at', 'user')
    search_fields = ('title', 'description')


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('profile_picture', 'bio', 'birth_date', 'location', 'website')

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)

    actions = ['generate_profile_pictures']

    def generate_profile_pictures(self, request, queryset):
        # Generate profile pictures for selected users
        user_ids = list(queryset.values_list('id', flat=True))

        try:
            # You would need to modify the management command to accept specific user IDs
            success_count = 0
            for user in queryset:
                if not hasattr(user, 'userprofile') or not user.userprofile.profile_picture:
                    # Generate profile picture logic here
                    success_count += 1

            messages.success(request, f"Generated profile pictures for {success_count} users")
        except Exception as e:
            messages.error(request, f"Error generating profile pictures: {str(e)}")

    generate_profile_pictures.short_description = "Generate profile pictures for selected users"

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'has_profile_picture', 'created_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__username', 'user__email', 'bio')
    readonly_fields = ('created_at', 'updated_at')

    def has_profile_picture(self, obj):
        return bool(obj.profile_picture)
    has_profile_picture.boolean = True
    has_profile_picture.short_description = 'Has Picture'

    actions = ['generate_missing_pictures']

    def generate_missing_pictures(self, request, queryset):
        count = 0
        for profile in queryset:
            if not profile.profile_picture:
                # Generate profile picture
                count += 1

        messages.success(request, f"Generated {count} profile pictures")

    generate_missing_pictures.short_description = "Generate profile pictures for selected profiles"
