# diary/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tags')

    def __str__(self):
        return self.name

class Entry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='entries')
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag, related_name='entries', blank=True)
    summary = models.TextField(blank=True, null=True)

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

class Biography(models.Model):
    """Generated user biography from multiple entries"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='biographies')
    title = models.CharField(max_length=200, default="My Life Story")
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    time_period_start = models.DateField(null=True, blank=True)
    time_period_end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'biographies'

    def __str__(self):
        return self.title

    def completion_percentage(self):
        """Calculate biography completion percentage"""
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
    """AI-generated insights about user patterns"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='insights')
    title = models.CharField(max_length=200)
    description = models.TextField()
    insight_type = models.CharField(max_length=50, choices=[
        ('pattern', 'Pattern'),
        ('suggestion', 'Suggestion'),
        ('achievement', 'Achievement'),
        ('mood', 'Mood Analysis')
    ])
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title
