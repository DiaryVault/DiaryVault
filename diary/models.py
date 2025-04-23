# diary/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django import forms
from django.apps import apps


class Tag(models.Model):
    name = models.CharField(max_length=50)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tags')

    class Meta:
        unique_together = ['name', 'user']

    def __str__(self):
        return self.name

class LifeChapter(models.Model):
    """Represents a custom chapter or category of a user's life"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='life_chapters')
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, default="sky-600")  # CSS color class

    def __str__(self):
        return self.title

    def entry_count(self):
        return self.entries.count()

class Entry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='diary_entries')
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag, related_name='entries', blank=True)
    mood = models.CharField(max_length=50, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    chapter = models.ForeignKey(LifeChapter, on_delete=models.SET_NULL, null=True, blank=True, related_name='entries')
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'entries'

    def __str__(self):
        return self.title

    def get_time_period(self):
        """Return the quarter and year of this entry for book organization"""
        date = self.created_at
        quarter = (date.month - 1) // 3 + 1
        return f"Q{quarter} {date.year}"

    def get_month_year(self):
        """Return month and year format for display"""
        return self.created_at.strftime("%b %Y")

class SummaryVersion(models.Model):
    """Track different versions of AI-generated summaries"""
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name='versions')
    summary = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Summary version for {self.entry.title} - {self.created_at}"

class Biography(models.Model):
    """Generated user biography from multiple entries"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='biographies')
    title = models.CharField(max_length=200, default="My Life Story")
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    time_period_start = models.DateField(null=True, blank=True)
    time_period_end = models.DateField(null=True, blank=True)
    chapters_data = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'biographies'

    def __str__(self):
        return self.title

    def completion_percentage(self):
        """Calculate biography completion percentage"""
        Entry = apps.get_model('diary', 'Entry')
        total_entries = Entry.objects.filter(user=self.user).count()
        if total_entries == 0:
            return 0
        time_period_entries = Entry.objects.filter(
            user=self.user,
            created_at__date__gte=self.time_period_start,
            created_at__date__lte=self.time_period_end
        ).count() if self.time_period_start and self.time_period_end else total_entries

        return min(int((time_period_entries / total_entries) * 100), 100)

class UserInsight(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='insights')
    insight_type = models.CharField(max_length=50, choices=[
        ('mood_analysis', 'Mood Analysis'),
        ('pattern', 'Pattern Detection'),
        ('suggestion', 'Suggestion'),
        ('topic_analysis', 'Topic Analysis')
    ])
    title = models.CharField(max_length=200)
    # Make sure this field exists
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.insight_type}: {self.title}"

    class Meta:
        ordering = ['-created_at']

class UserPreference(models.Model):
    """Store user personalization preferences for journal generation"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='journal_preferences')
    writing_style = models.CharField(max_length=30, default='reflective',
                                    choices=[
                                        ('reflective', 'Reflective'),
                                        ('analytical', 'Analytical'),
                                        ('creative', 'Creative'),
                                        ('concise', 'Concise'),
                                        ('detailed', 'Detailed'),
                                        ('poetic', 'Poetic'),
                                        ('humorous', 'Humorous'),
                                    ])
    tone = models.CharField(max_length=30, default='balanced',
                           choices=[
                               ('positive', 'Mostly Positive'),
                               ('balanced', 'Balanced'),
                               ('realistic', 'Realistic'),
                               ('growth', 'Growth-focused'),
                           ])
    focus_areas = models.CharField(max_length=255, blank=True,
                                  help_text="Comma-separated areas to emphasize (e.g., personal growth,relationships)")
    language_complexity = models.CharField(max_length=20, default='moderate',
                                         choices=[
                                             ('simple', 'Simple'),
                                             ('moderate', 'Moderate'),
                                             ('advanced', 'Advanced'),
                                         ])
    include_questions = models.BooleanField(default=True,
                                          help_text="Include reflective questions at the end of entries")
    metaphor_frequency = models.CharField(max_length=20, default='occasional',
                                        choices=[
                                            ('minimal', 'Minimal'),
                                            ('occasional', 'Occasional'),
                                            ('frequent', 'Frequent'),
                                        ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user.username}"

    def get_focus_areas_list(self):
        """Return focus areas as a list"""
        if not self.focus_areas:
            return []
        return [area.strip() for area in self.focus_areas.split(',')]

    class Meta:
        verbose_name = "User Preference"
        verbose_name_plural = "User Preferences"

class EntryForm(forms.ModelForm):
    # Add a field for tags that will be processed separately
    tags = forms.CharField(required=False, help_text="Comma-separated tags")

    class Meta:
        model = Entry
        fields = ['title', 'content', 'mood', 'chapter']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'diary-font'}),
        }

    def __init__(self, *args, **kwargs):
        # Extract user from kwargs so we can use it later
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # If this is an existing entry, populate the tags field
        if self.instance and self.instance.pk:
            self.initial['tags'] = ', '.join([tag.name for tag in self.instance.tags.all()])

    def save(self, commit=True, user=None):
        # Use either the user passed to save() or the one set during initialization
        user = user or self.user
        if not user:
            raise ValueError("User must be provided to save the form")

        # Save the entry but don't commit until we handle the tags
        entry = super().save(commit=False)
        entry.user = user

        if commit:
            entry.save()

            # Process tags field
            if 'tags' in self.cleaned_data:
                tag_names = [t.strip() for t in self.cleaned_data['tags'].split(',') if t.strip()]

                # Clear existing tags for this entry
                entry.tags.clear()

                # Add each tag, creating new ones as needed
                for tag_name in tag_names:
                    tag, created = Tag.objects.get_or_create(
                        name=tag_name,
                        user=user  # This links the tag to the user
                    )
                    entry.tags.add(tag)

        return entry
class EntryTag(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name='entry_tags')
    name = models.CharField(max_length=50)
    tag_type = models.CharField(max_length=20, default='topic', choices=[
        ('topic', 'Topic'),
        ('mood', 'Mood'),
        ('person', 'Person'),
        ('location', 'Location'),
        ('other', 'Other')
    ])

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

