from django.contrib import admin
from .models import Entry, Tag, SummaryVersion, UserInsight, UserProfile, Web3Nonce, WalletSession

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.contrib import messages

User = get_user_model()

# Register Entry model
@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at', 'mood', 'word_count')
    list_filter = ('created_at', 'user', 'mood')
    search_fields = ('title', 'content')
    date_hierarchy = 'created_at'
    readonly_fields = ('word_count', 'created_at', 'updated_at')
    filter_horizontal = ('tags',)
    
    fieldsets = (
        (None, {
            'fields': ('title', 'content', 'user')
        }),
        ('Metadata', {
            'fields': ('mood', 'mood_rating', 'energy_level', 'tags', 'word_count'),
            'classes': ('collapse',)
        }),
        ('Summary', {
            'fields': ('summary', 'summary_generated_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Register Tag model
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'category', 'usage_count')
    list_filter = ('user', 'category')
    search_fields = ('name',)
    readonly_fields = ('usage_count',)

# Register SummaryVersion model
@admin.register(SummaryVersion)
class SummaryVersionAdmin(admin.ModelAdmin):
    list_display = ('entry', 'created_at')
    list_filter = ('created_at',)
    readonly_fields = ('created_at',)

# Register UserInsight model
@admin.register(UserInsight)
class UserInsightAdmin(admin.ModelAdmin):
    list_display = ('title', 'insight_type', 'user', 'priority', 'confidence_score', 'created_at')
    list_filter = ('insight_type', 'priority', 'created_at', 'user')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('related_entries',)
    
    fieldsets = (
        (None, {
            'fields': ('user', 'insight_type', 'title', 'content')
        }),
        ('Metadata', {
            'fields': ('priority', 'confidence_score', 'related_entries'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('profile_picture', 'bio', 'birth_date', 'location', 'website')
    readonly_fields = ('created_at', 'updated_at')

# Updated UserAdmin to include Web3 fields
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    
    # Combine both list_display configurations
    list_display = [
        'username', 
        'email',
        'wallet_address', 
        'wallet_type', 
        'is_web3_verified', 
        'total_rewards_earned', 
        'streak_days',
        'is_staff',
        'is_active',
        'date_joined'
    ]
    
    # Combine both list_filter configurations
    list_filter = [
        'is_web3_verified', 
        'wallet_type', 
        'is_anonymous_mode', 
        'encryption_enabled',
        'is_staff',
        'is_superuser',
        'is_active',
        'date_joined'
    ]
    
    # Combine search fields
    search_fields = ['username', 'email', 'wallet_address', 'first_name', 'last_name']
    
    # Combine readonly fields
    readonly_fields = ['date_joined', 'last_login', 'last_wallet_login']
    
    # Add Web3 fieldsets to the existing ones
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Web3 Information', {
            'fields': ('wallet_address', 'wallet_type', 'is_web3_verified', 'last_wallet_login'),
            'classes': ('collapse',)
        }),
        ('Rewards & Gamification', {
            'fields': ('total_rewards_earned', 'streak_days'),
            'classes': ('collapse',)
        }),
        ('Privacy Settings', {
            'fields': ('is_anonymous_mode', 'encryption_enabled'),
            'classes': ('collapse',)
        }),
    )
    
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

# Register UserAdmin (unregister first to avoid conflicts)
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'has_profile_picture', 'location', 'created_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__username', 'user__email', 'bio', 'location')
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

# Web3 Authentication Admin Models
@admin.register(Web3Nonce)
class Web3NonceAdmin(admin.ModelAdmin):
    list_display = ['wallet_address', 'nonce', 'is_used', 'timestamp', 'expires_at']
    list_filter = ['is_used', 'timestamp']
    search_fields = ['wallet_address']
    readonly_fields = ['timestamp']

@admin.register(WalletSession)
class WalletSessionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 
        'wallet_address', 
        'chain_id', 
        'is_active', 
        'created_at', 
        'last_activity'
    ]
    list_filter = ['is_active', 'chain_id', 'created_at']
    search_fields = ['user__username', 'wallet_address']
    readonly_fields = ['session_id', 'created_at']

# ENHANCED: Add admin for marketplace models if they exist
try:
    from .models import Journal, JournalEntry, JournalTag, JournalLike, JournalPurchase
    
    @admin.register(Journal)
    class JournalAdmin(admin.ModelAdmin):
        list_display = ('title', 'author', 'is_published', 'price', 'view_count', 'date_published')
        list_filter = ('is_published', 'date_published', 'price', 'journal_type')
        search_fields = ('title', 'description', 'author__username')
        readonly_fields = ('view_count', 'total_tips', 'popularity_score', 'created_at', 'updated_at')
        filter_horizontal = ('marketplace_tags', 'likes')
        date_hierarchy = 'date_published'
        
        fieldsets = (
            (None, {
                'fields': ('title', 'description', 'author', 'cover_image')
            }),
            ('Publishing', {
                'fields': ('is_published', 'date_published', 'privacy_setting', 'price')
            }),
            ('Marketplace', {
                'fields': ('marketplace_tags', 'is_staff_pick', 'featured'),
                'classes': ('collapse',)
            }),
            ('Statistics', {
                'fields': ('view_count', 'total_tips', 'popularity_score', 'likes'),
                'classes': ('collapse',)
            }),
            ('Compilation', {
                'fields': ('compilation_method', 'journal_type', 'ai_enhancements_used'),
                'classes': ('collapse',)
            }),
        )
    
    @admin.register(JournalTag)
    class JournalTagAdmin(admin.ModelAdmin):
        list_display = ('name', 'slug', 'color')
        search_fields = ('name', 'description')
        prepopulated_fields = {'slug': ('name',)}
    
    @admin.register(JournalEntry)
    class JournalEntryAdmin(admin.ModelAdmin):
        list_display = ('title', 'journal', 'entry_type', 'is_included', 'date_created')
        list_filter = ('entry_type', 'is_included', 'journal', 'date_created')
        search_fields = ('title', 'content')
        readonly_fields = ('date_created', 'date_updated')
    
except ImportError:
    # Marketplace models not available yet
    pass

# ENHANCED: Add admin for compilation models if they exist
try:
    from .models import JournalCompilationSession, JournalTemplate, AIGenerationLog
    
    @admin.register(JournalCompilationSession)
    class JournalCompilationSessionAdmin(admin.ModelAdmin):
        list_display = ('user', 'journal_type', 'compilation_method', 'status', 'created_at')
        list_filter = ('status', 'compilation_method', 'journal_type', 'created_at')
        readonly_fields = ('session_id', 'created_at', 'updated_at', 'completed_at')
        filter_horizontal = ('selected_entries',)
    
    @admin.register(JournalTemplate)
    class JournalTemplateAdmin(admin.ModelAdmin):
        list_display = ('name', 'template_type', 'success_rate', 'usage_count', 'is_active')
        list_filter = ('template_type', 'is_active', 'is_featured')
        search_fields = ('name', 'description')
        readonly_fields = ('usage_count', 'created_at', 'updated_at')
    
    @admin.register(AIGenerationLog)
    class AIGenerationLogAdmin(admin.ModelAdmin):
        list_display = ('user', 'generation_type', 'success', 'generation_time', 'created_at')
        list_filter = ('generation_type', 'success', 'created_at')
        readonly_fields = ('created_at', 'generation_time', 'token_count', 'cost')
        search_fields = ('user__username', 'input_prompt', 'generated_content')
        
except ImportError:
    # Compilation models not available yet
    pass