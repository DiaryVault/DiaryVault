# diary/models.py
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class Tag(models.Model):
    name = models.CharField(max_length=50)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tags')

    # IMPROVED: Add tag categories for better organization
    TAG_CATEGORIES = [
        ('emotion', 'Emotion'),
        ('activity', 'Activity'),
        ('person', 'Person'),
        ('location', 'Location'),
        ('goal', 'Goal'),
        ('challenge', 'Challenge'),
        ('achievement', 'Achievement'),
        ('other', 'Other'),
    ]
    category = models.CharField(max_length=20, choices=TAG_CATEGORIES, default='other')

    # IMPROVED: Track tag usage for insights
    usage_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        unique_together = ['name', 'user']
        indexes = [
            models.Index(fields=['user', 'category']),
            models.Index(fields=['user', 'usage_count']),
        ]

    def update_usage_count(self):
        """Update the usage count based on related entries"""
        self.usage_count = self.entries.count()
        self.save(update_fields=['usage_count'])

    def __str__(self):
        return self.name

class LifeChapter(models.Model):
    """Represents a custom chapter or category of a user's life"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='life_chapters')
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, default="indigo")  # CSS color class
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']

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

    # IMPROVED: Add choices for consistent mood data
    MOOD_CHOICES = [
        ('excited', 'Excited'),
        ('happy', 'Happy'),
        ('content', 'Content'),
        ('neutral', 'Neutral'),
        ('anxious', 'Anxious'),
        ('sad', 'Sad'),
        ('angry', 'Angry'),
        ('confused', 'Confused'),
        ('grateful', 'Grateful'),
        ('overwhelmed', 'Overwhelmed'),
    ]
    mood = models.CharField(max_length=50, choices=MOOD_CHOICES, blank=True, null=True)

    # IMPROVED: Add numeric mood rating for better trend analysis
    mood_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
        help_text="Rate your mood from 1 (terrible) to 10 (amazing)"
    )

    # IMPROVED: Add energy level for richer insights
    energy_level = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
        help_text="Rate your energy level from 1 (exhausted) to 10 (energized)"
    )

    # IMPROVED: Add word count for writing analysis
    word_count = models.PositiveIntegerField(default=0, editable=False)

    summary = models.TextField(blank=True, null=True)
    summary_generated_at = models.DateTimeField(null=True, blank=True)
    chapter = models.ForeignKey(LifeChapter, on_delete=models.SET_NULL, null=True, blank=True, related_name='entries')

    # Marketplace integration - link to published journal
    published_in_journal = models.ForeignKey('Journal', on_delete=models.SET_NULL, null=True, blank=True, related_name='source_entries')

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'entries'
        # ENHANCED: Add comprehensive database indexes for better query performance
        indexes = [
            # Basic indexes
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['user', 'mood']),
            models.Index(fields=['created_at']),
            models.Index(fields=['user', 'mood_rating']),
            # Marketplace filtering
            models.Index(fields=['user', 'published_in_journal']),
            # Chapter filtering
            models.Index(fields=['user', 'chapter']),
            # Analytics
            models.Index(fields=['word_count']),
            # Composite indexes for common filter combinations
            models.Index(fields=['user', 'mood', 'created_at']),
            models.Index(fields=['user', 'chapter', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        # Auto-calculate word count
        if self.content:
            self.word_count = len(self.content.split())
        super().save(*args, **kwargs)

        # Update tag usage counts
        for tag in self.tags.all():
            tag.update_usage_count()

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

    def can_be_published(self):
        """Check if entry meets publishing criteria"""
        return (
            len(self.content.strip()) >= 100 and  # Minimum length
            self.title.strip() and  # Has title
            not self.published_in_journal  # Not already published
        )

    def get_quality_score(self):
        """Calculate quality score for this entry"""
        score = 0

        # Length factor (40 points max)
        word_count = len(self.content.split())
        if word_count >= 300:
            score += 40
        elif word_count >= 150:
            score += 30
        elif word_count >= 100:
            score += 20
        elif word_count >= 50:
            score += 10

        # Has mood (20 points)
        if self.mood:
            score += 20

        # Has tags (20 points)
        if self.tags.exists():
            score += 20

        # Has title (10 points)
        if self.title.strip():
            score += 10

        # Engagement factor (10 points)
        if hasattr(self, 'photos') and self.photos.exists():
            score += 5
        if hasattr(self, 'chapter') and self.chapter:
            score += 5

        return min(100, score)

    # Compatibility aliases
    def can_publish(self):
        """Compatibility alias for can_be_published"""
        return self.can_be_published()

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
        from django.apps import apps
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
        ('topic_analysis', 'Topic Analysis'),
        ('writing_style', 'Writing Style Analysis'),
        ('emotional_trends', 'Emotional Trends'),
        ('productivity', 'Productivity Insights'),
    ])
    title = models.CharField(max_length=200)
    content = models.TextField()

    # IMPROVED: Add confidence score for AI insights
    confidence_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="AI confidence in this insight (0.0 to 1.0)"
    )

    # IMPROVED: Track which entries contributed to this insight
    related_entries = models.ManyToManyField(Entry, blank=True, related_name='insights')

    # IMPROVED: Add priority for displaying insights
    priority = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ], default='medium')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.insight_type}: {self.title}"

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['user', 'insight_type']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['user', 'priority']),
        ]
        # ENHANCED: Add data integrity constraints
        constraints = [
            models.CheckConstraint(
                check=models.Q(confidence_score__gte=0.0) & models.Q(confidence_score__lte=1.0),
                name='valid_confidence_score'
            ),
        ]

class AnalyticsEvent(models.Model):
    """Track user interactions for better insights"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analytics_events')
    event_type = models.CharField(max_length=50, choices=[
        ('entry_created', 'Entry Created'),
        ('entry_updated', 'Entry Updated'),
        ('mood_logged', 'Mood Logged'),
        ('tags_added', 'Tags Added'),
        ('insights_viewed', 'Insights Viewed'),
        ('insights_regenerated', 'Insights Regenerated'),
    ])
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'event_type', 'timestamp']),
        ]

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

# ========================================================================
# SMART JOURNAL COMPILER MODELS
# ========================================================================

class JournalCompilationSession(models.Model):
    """Track journal compilation sessions for analytics and recovery"""

    COMPILATION_METHODS = [
        ('ai', 'AI Smart Compilation'),
        ('thematic', 'Thematic Collection'),
        ('chronological', 'Timeline Journey'),
    ]

    JOURNAL_TYPES = [
        ('growth', 'Personal Growth'),
        ('travel', 'Travel & Adventures'),
        ('career', 'Career Development'),
        ('relationships', 'Relationships & Love'),
        ('creative', 'Creative Process'),
        ('health', 'Health & Wellness'),
        ('family', 'Family Life'),
        ('learning', 'Learning & Education'),
    ]

    STATUS_CHOICES = [
        ('started', 'Started'),
        ('analyzing', 'Analyzing'),
        ('structuring', 'Generating Structure'),
        ('ready', 'Ready to Publish'),
        ('published', 'Published'),
        ('abandoned', 'Abandoned'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='compilation_sessions')
    session_id = models.UUIDField(default=uuid.uuid4, unique=True)

    # Compilation settings
    compilation_method = models.CharField(max_length=20, choices=COMPILATION_METHODS)
    journal_type = models.CharField(max_length=20, choices=JOURNAL_TYPES)

    # Selected entries
    selected_entries = models.ManyToManyField(Entry, blank=True)

    # AI enhancements
    ai_enhancements = models.JSONField(default=list, blank=True)

    # Generated structure
    generated_structure = models.JSONField(default=dict, blank=True)

    # Analysis results
    analysis_results = models.JSONField(default=dict, blank=True)

    # Session metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Final journal if published
    published_journal = models.ForeignKey('Journal', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Journal Compilation Session'
        verbose_name_plural = 'Journal Compilation Sessions'

    def __str__(self):
        return f"{self.user.username} - {self.get_journal_type_display()} ({self.status})"

    def get_progress_percentage(self):
        """Calculate completion percentage"""
        status_progress = {
            'started': 10,
            'analyzing': 30,
            'structuring': 60,
            'ready': 90,
            'published': 100,
            'abandoned': 0
        }
        return status_progress.get(self.status, 0)

    def mark_as_completed(self, journal=None):
        """Mark session as completed"""
        self.status = 'published' if journal else 'ready'
        self.completed_at = timezone.now()
        if journal:
            self.published_journal = journal
        self.save()

class JournalTemplate(models.Model):
    """Predefined journal templates for compilation"""

    TEMPLATE_TYPES = [
        ('transformation', 'Personal Transformation'),
        ('adventure', 'Adventure & Travel'),
        ('creative', 'Creative Journey'),
        ('reflection', 'Mindful Reflection'),
        ('relationship', 'Relationship Chronicles'),
        ('career', 'Professional Development'),
        ('custom', 'Custom Template'),
    ]

    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    description = models.TextField()

    # Template structure
    chapter_structure = models.JSONField(default=list)  # [{'title': 'Chapter 1', 'description': '...', 'theme': 'growth'}]

    # Template metadata
    success_rate = models.IntegerField(default=85, validators=[MinValueValidator(0), MaxValueValidator(100)])
    average_price = models.DecimalField(max_digits=6, decimal_places=2, default=9.99)
    estimated_word_count = models.IntegerField(default=5000)

    # Template usage
    usage_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    # Template creation
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-success_rate', '-usage_count']
        verbose_name = 'Journal Template'
        verbose_name_plural = 'Journal Templates'

    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

    def increment_usage(self):
        """Increment usage count"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])

class JournalAnalytics(models.Model):
    """Analytics for published journals from compiler"""

    journal = models.OneToOneField('Journal', on_delete=models.CASCADE, related_name='analytics')

    # Compilation metadata
    compilation_method = models.CharField(max_length=20, blank=True)
    journal_type = models.CharField(max_length=20, blank=True)
    template_used = models.ForeignKey(JournalTemplate, on_delete=models.SET_NULL, null=True, blank=True)

    # Content analytics
    total_words = models.IntegerField(default=0)
    total_entries = models.IntegerField(default=0)
    average_entry_length = models.IntegerField(default=0)

    # Quality metrics
    quality_score = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    readability_score = models.FloatField(default=0)
    theme_diversity = models.IntegerField(default=0)

    # Performance metrics
    view_count_weekly = models.IntegerField(default=0)
    like_count_weekly = models.IntegerField(default=0)
    purchase_count_weekly = models.IntegerField(default=0)
    revenue_weekly = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    # Reader engagement
    average_read_time = models.IntegerField(default=0)  # in seconds
    completion_rate = models.FloatField(default=0)  # percentage of readers who finish

    # Market performance
    conversion_rate = models.FloatField(default=0)  # views to purchases
    reader_rating = models.FloatField(default=0)

    # Analytics timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_calculated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Journal Analytics'
        verbose_name_plural = 'Journal Analytics'

    def __str__(self):
        return f"Analytics for {self.journal.title}"

    def calculate_metrics(self):
        """Calculate and update analytics metrics"""
        # Update view counts, engagement, etc.
        # This would be called periodically or triggered by events
        pass

class AIGenerationLog(models.Model):
    """Log AI generations for debugging and improvement"""

    GENERATION_TYPES = [
        ('analysis', 'Entry Analysis'),
        ('structure', 'Journal Structure'),
        ('introduction', 'Chapter Introduction'),
        ('questions', 'Reflection Questions'),
        ('connections', 'Thematic Connections'),
        ('guide', 'Reader\'s Guide'),
        ('marketing', 'Marketing Copy'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    generation_type = models.CharField(max_length=20, choices=GENERATION_TYPES)

    # Input data
    input_prompt = models.TextField()
    input_metadata = models.JSONField(default=dict, blank=True)

    # Output data
    generated_content = models.TextField()
    generation_metadata = models.JSONField(default=dict, blank=True)

    # Quality metrics
    success = models.BooleanField(default=True)
    user_rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])

    # Performance metrics
    generation_time = models.FloatField(default=0)  # in seconds
    token_count = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=6, decimal_places=4, default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI Generation Log'
        verbose_name_plural = 'AI Generation Logs'

    def __str__(self):
        return f"{self.get_generation_type_display()} for {self.user.username}"

# ========================================================================
# MARKETPLACE-SPECIFIC MODELS (ENHANCED)
# ========================================================================

class JournalTag(models.Model):
    """Enhanced tags for marketplace journals"""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, default='blue')

    def __str__(self):
        return self.name

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
    featured = models.BooleanField(default=False)

    # Marketplace enhancements
    price = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    marketplace_tags = models.ManyToManyField(JournalTag, blank=True)

    # Statistics
    view_count = models.PositiveIntegerField(default=0)
    total_tips = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    popularity_score = models.FloatField(default=0)  # Calculated field based on views, likes, comments, etc.

    # Cached counts for performance
    like_count_cached = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    entry_count_cached = models.PositiveIntegerField(default=0)

    # Content metadata
    first_entry_date = models.DateField(null=True, blank=True)
    last_entry_date = models.DateField(null=True, blank=True)

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

    # ENHANCED: Journal Compiler Integration
    compilation_session = models.ForeignKey(
        JournalCompilationSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='compiled_journals'
    )

    # Compilation metadata
    compilation_method = models.CharField(max_length=20, blank=True)
    journal_type = models.CharField(max_length=20, blank=True)
    ai_enhancements_used = models.JSONField(default=list, blank=True)

    # AI-generated content flags
    has_ai_introductions = models.BooleanField(default=False)
    has_ai_questions = models.BooleanField(default=False)
    has_ai_connections = models.BooleanField(default=False)
    has_readers_guide = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # ENHANCED: Add comprehensive database indexes for marketplace queries
        indexes = [
            # Basic marketplace filtering
            models.Index(fields=['is_published', 'date_published']),
            models.Index(fields=['is_published', 'price']),
            models.Index(fields=['author', 'is_published']),
            models.Index(fields=['is_published', 'popularity_score']),
            models.Index(fields=['is_published', 'view_count']),
            models.Index(fields=['is_published', 'like_count_cached']),
            # Advanced marketplace filtering
            models.Index(fields=['is_published', 'privacy_setting', 'date_published']),
            models.Index(fields=['is_published', 'journal_type', 'date_published']),
            # Search functionality
            models.Index(fields=['is_published', 'title']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Set date_published when publishing for the first time
        if self.is_published and self.date_published is None:
            self.date_published = timezone.now()
        super().save(*args, **kwargs)

    def like_count(self):
        return self.likes.count()

    @property
    def is_premium(self):
        return self.price > 0

    @property
    def author_display_name(self):
        return self.author.get_full_name() or self.author.username

    def update_cached_counts(self):
        """Update cached statistics"""
        self.like_count_cached = self.journal_likes.count() if hasattr(self, 'journal_likes') else self.likes.count()
        self.review_count = self.reviews.count() if hasattr(self, 'reviews') else 0
        self.entry_count_cached = self.entries.count()

        # Update entry dates
        if self.entries.exists():
            dates = self.entries.aggregate(
                first=models.Min('date_created'),
                last=models.Max('date_created')
            )
            self.first_entry_date = dates['first'].date() if dates['first'] else None
            self.last_entry_date = dates['last'].date() if dates['last'] else None

        self.save(update_fields=['like_count_cached', 'review_count', 'entry_count_cached',
                               'first_entry_date', 'last_entry_date'])

    def calculate_popularity(self):
        """Calculate popularity score based on various metrics"""
        view_weight = 0.2
        like_weight = 1.0
        comment_weight = 1.5
        tip_weight = 5.0

        try:
            comment_count = Comment.objects.filter(journal=self).count()
        except:
            comment_count = 0

        score = (self.view_count * view_weight +
                self.likes.count() * like_weight +
                comment_count * comment_weight +
                float(self.total_tips) * tip_weight)

        self.popularity_score = score
        self.save(update_fields=['popularity_score'])
        return score

    def get_compilation_analytics(self):
        """Get analytics for this compiled journal"""
        try:
            return self.analytics
        except JournalAnalytics.DoesNotExist:
            return JournalAnalytics.objects.create(journal=self)

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

    # ENHANCED: Journal Compiler Integration
    ENTRY_TYPES = [
        ('original', 'Original Entry'),
        ('introduction', 'Chapter Introduction'),
        ('reflection', 'Reflection Questions'),
        ('guide', 'Reader\'s Guide'),
        ('connection', 'Thematic Connection'),
    ]

    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='original')
    original_entry = models.ForeignKey(
        Entry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='published_versions'
    )

    # AI generation metadata
    is_ai_generated = models.BooleanField(default=False)
    ai_generation_log = models.ForeignKey(
        AIGenerationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    def __str__(self):
        return self.title

class JournalLike(models.Model):
    """Track likes for journals"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='journal_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'journal']

class JournalPurchase(models.Model):
    """Track premium journal purchases"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='purchases')
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'journal']
        # ENHANCED: Add indexes for purchase analytics
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['journal', 'created_at']),
            models.Index(fields=['journal__author', 'created_at']),  # For author earnings
        ]

class JournalReview(models.Model):
    """Reviews and ratings for journals"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    review_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'journal']

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
        tipper_name = self.tipper.username if self.tipper else "Anonymous"
        recipient_name = self.recipient.username if self.recipient else "Unknown"
        return f"${self.amount} tip from {tipper_name} to {recipient_name}"

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

class EntryPhoto(models.Model):
    """Model for photos attached to journal entries"""
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name='photos')
    photo = models.ImageField(upload_to='entry_photos/%Y/%m/%d/')
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.entry.title}"

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

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True,
        help_text="User's profile picture"
    )
    bio = models.TextField(max_length=500, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def get_profile_picture_url(self):
        if self.profile_picture and hasattr(self.profile_picture, 'url'):
            return self.profile_picture.url
        return '/static/images/default-avatar.png'  # Fallback image

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

class MarketplacePlacement(models.Model):
    """Track premium placements for journals"""
    journal = models.ForeignKey('Journal', on_delete=models.CASCADE, related_name='placements')
    placement_type = models.CharField(max_length=50, choices=[
        ('featured_homepage', 'Featured Homepage'),
        ('category_spotlight', 'Category Spotlight'),
        ('newsletter_feature', 'Newsletter Feature'),
        ('search_boost', 'Search Boost'),
    ])
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

class UserSubscription(models.Model):
    """Handle various subscription tiers"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='marketplace_subscription')
    subscription_type = models.CharField(max_length=30, choices=[
        ('reader_basic', 'Reader Basic'),
        ('reader_premium', 'Reader Premium'),
        ('author_starter', 'Author Starter'),
        ('author_professional', 'Author Professional'),
    ])
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(auto_now_add=True)
    next_billing_date = models.DateTimeField()
    stripe_subscription_id = models.CharField(max_length=255, blank=True)

    def get_benefits(self):
        """Return subscription benefits"""
        try:
            from .services.advanced_marketplace_service import MarketplaceEnhancementService
            tiers = MarketplaceEnhancementService.implement_subscription_tiers()
            return tiers.get(self.subscription_type, {}).get('benefits', [])
        except:
            return []

class AnalyticsPackage(models.Model):
    """Track purchases of premium analytics"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analytics_purchases')
    package_type = models.CharField(max_length=50, choices=[
        ('basic_insights', 'Basic Insights'),
        ('advanced_analytics', 'Advanced Analytics'),
        ('market_intelligence', 'Market Intelligence'),
    ])
    data = models.JSONField()  # Store the analytics data
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2)
    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
