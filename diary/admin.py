from django.contrib import admin
from .models import Entry, Tag, SummaryVersion, LifeChapter, Biography, UserInsight

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
