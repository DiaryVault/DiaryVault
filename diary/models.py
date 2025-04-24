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

class Journal(models.Model):
    """Model representing a curated journal that can be published to the marketplace"""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='journals')
    cover_image = models.ImageField(upload_to='journal_covers/', blank=True, null=True)

    # Marketplace specific fields
    is_published = models.BooleanField(default=False)
    date_published = models.DateTimeField(null=True, blank=True)
    is_staff_pick = models.BooleanField(default=False)
    featured_rank = models.IntegerField(null=True, blank=True)

    # Statistics
    view_count = models.PositiveIntegerField(default=0)
    total_tips = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    popularity_score = models.FloatField(default=0)  # Calculated field based on views, likes, comments, etc.

    # Likes (many-to-many relationship with User)
    likes = models.ManyToManyField(User, related_name='liked_journals', blank=True)

    # Contest fields
    contest_participant = models.BooleanField(default=False)
    contest_score = models.FloatField(default=0)

    # Privacy settings
    PRIVACY_CHOICES = [
        ('public', 'Public'),
        ('community', 'Community Only'),
        ('restricted', 'Restricted'),
    ]
    privacy_setting = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default='public')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Set date_published when publishing for the first time
        if self.is_published and self.date_published is None:
            self.date_published = timezone.now()
        super().save(*args, **kwargs)

    def like_count(self):
        return self.likes.count()

    def calculate_popularity(self):
        """Calculate popularity score based on various metrics"""
        # Example formula: views * 0.2 + likes * 1.0 + comments * 1.5 + tips * 5.0
        # This would need to be implemented based on your specific requirements
        view_weight = 0.2
        like_weight = 1.0
        comment_weight = 1.5
        tip_weight = 5.0

        comment_count = Comment.objects.filter(journal=self).count()

        score = (self.view_count * view_weight +
                self.likes.count() * like_weight +
                comment_count * comment_weight +
                float(self.total_tips) * tip_weight)

        self.popularity_score = score
        self.save(update_fields=['popularity_score'])
        return score

class JournalEntry(models.Model):
    """Model representing an individual entry in a journal"""

    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='entries')
    title = models.CharField(max_length=255)
    content = models.TextField()

    # Entry metadata
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    # Optional entry date (for when the event took place)
    entry_date = models.DateField(null=True, blank=True)

    # Include in published journal
    is_included = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class Comment(models.Model):
    """Model for comments on journals"""

    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username} on {self.journal.title}"

class Tip(models.Model):
    """Model for tracking tips received by journal authors"""

    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='tips')
    tipper = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tips_given')
    recipient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tips_received')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=255, blank=True, null=True)  # For payment processor reference
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"${self.amount} tip from {self.tipper.username} to {self.recipient.username}"

    def save(self, *args, **kwargs):
        # Update the journal's total_tips field when a new tip is saved
        super().save(*args, **kwargs)

        # Update journal total tips
        journal = self.journal
        total_tips = Tip.objects.filter(journal=journal).aggregate(models.Sum('amount'))['amount__sum'] or 0
        journal.total_tips = total_tips
        journal.save(update_fields=['total_tips'])

        # Recalculate journal popularity
        journal.calculate_popularity()

class ContestEntry(models.Model):
    """Model for tracking journal entries in weekly contests"""

    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='contest_entries')
    contest_start_date = models.DateField()
    contest_end_date = models.DateField()
    final_rank = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('journal', 'contest_start_date')

    def __str__(self):
        return f"{self.journal.title} in contest {self.contest_start_date} to {self.contest_end_date}"

class UserFollowing(models.Model):
    """Model for tracking which users follow each other"""
    user = models.ForeignKey(User, related_name='following', on_delete=models.CASCADE)
    followed_user = models.ForeignKey(User, related_name='followers', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'followed_user')

    def __str__(self):
        return f"{self.user.username} follows {self.followed_user.username}"
