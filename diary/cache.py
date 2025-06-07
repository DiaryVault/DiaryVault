# diary/cache.py - Complete caching strategy
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Count, Sum, Avg, Min, Max
from django.utils import timezone
from datetime import timedelta
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

class CacheKeys:
    """Centralized cache key management"""

    # User-specific caches
    USER_INSIGHTS = "user_insights_{user_id}"
    USER_STATS = "user_stats_{user_id}"
    USER_DASHBOARD = "dashboard_{user_id}"
    USER_WRITING_STREAK = "writing_streak_{user_id}"
    USER_ENTRIES_COUNT = "user_entries_count_{user_id}"
    USER_MOOD_DISTRIBUTION = "user_mood_dist_{user_id}"

    # Marketplace caches
    MARKETPLACE_FEATURED = "marketplace_featured"
    MARKETPLACE_STATS = "marketplace_stats"
    MARKETPLACE_TRENDING = "marketplace_trending"
    MARKETPLACE_NEW_RELEASES = "marketplace_new_releases"
    MARKETPLACE_TOP_EARNING = "marketplace_top_earning"
    MARKETPLACE_POPULAR_FREE = "marketplace_popular_free"

    # Journal-specific caches
    JOURNAL_ANALYTICS = "journal_analytics_{journal_id}"
    JOURNAL_SIMILAR = "journal_similar_{journal_id}"
    JOURNAL_REVIEWS = "journal_reviews_{journal_id}"

    # Global caches
    POPULAR_TAGS = "popular_tags"
    GLOBAL_STATS = "global_stats"
    AI_USAGE_STATS = "ai_usage_stats"

    # Smart compiler caches
    JOURNAL_STRUCTURE = "journal_structure_{hash}"
    COMPILATION_ANALYSIS = "compilation_analysis_{hash}"
    TEMPLATE_DATA = "journal_templates"

    @staticmethod
    def user_library(user_id, filters_hash=None):
        """Cache key for user's library view with filters"""
        if filters_hash:
            return f"library_{user_id}_{filters_hash}"
        return f"library_{user_id}"

    @staticmethod
    def marketplace_category(category, sort_by='trending'):
        """Cache key for marketplace category pages"""
        return f"marketplace_{category}_{sort_by}"

    @staticmethod
    def user_published_journals(user_id):
        """Cache key for user's published journals"""
        return f"published_journals_{user_id}"

class CacheService:
    """Service for managing application caching"""

    # Cache timeout constants
    TIMEOUT_SHORT = 300      # 5 minutes
    TIMEOUT_MEDIUM = 1800    # 30 minutes
    TIMEOUT_LONG = 3600      # 1 hour
    TIMEOUT_VERY_LONG = 86400 # 24 hours

    @staticmethod
    def get_user_insights(user):
        """Get cached user insights"""
        cache_key = CacheKeys.USER_INSIGHTS.format(user_id=user.id)
        insights = cache.get(cache_key)

        if insights is None:
            from .models import UserInsight
            insights = list(UserInsight.objects.filter(user=user).order_by('-created_at'))
            cache.set(cache_key, insights, CacheService.TIMEOUT_MEDIUM)
            logger.debug(f"Cached insights for user {user.id}")

        return insights

    @staticmethod
    def invalidate_user_insights(user):
        """Invalidate user insights cache"""
        cache_key = CacheKeys.USER_INSIGHTS.format(user_id=user.id)
        cache.delete(cache_key)
        logger.debug(f"Invalidated insights cache for user {user.id}")

    @staticmethod
    def get_user_stats(user):
        """Get cached user statistics"""
        cache_key = CacheKeys.USER_STATS.format(user_id=user.id)
        stats = cache.get(cache_key)

        if stats is None:
            from .models import Entry

            # Calculate comprehensive stats
            entries = Entry.objects.filter(user=user)
            entry_data = entries.aggregate(
                total_entries=Count('id'),
                total_words=Sum('word_count'),
                avg_words=Avg('word_count'),
                avg_mood_rating=Avg('mood_rating'),
                first_entry=Min('created_at'),
                last_entry=Max('created_at')
            )

            # Calculate additional stats
            stats = {
                'total_entries': entry_data['total_entries'] or 0,
                'total_words': entry_data['total_words'] or 0,
                'avg_words_per_entry': int(entry_data['avg_words'] or 0),
                'avg_mood_rating': round(entry_data['avg_mood_rating'] or 0, 1),
                'first_entry_date': entry_data['first_entry'],
                'last_entry_date': entry_data['last_entry'],
                'writing_streak': CacheService._calculate_writing_streak(user),
                'entries_this_month': entries.filter(
                    created_at__gte=timezone.now().replace(day=1)
                ).count(),
                'most_used_mood': CacheService._get_most_used_mood(user),
                'favorite_tags': CacheService._get_favorite_tags(user),
            }

            cache.set(cache_key, stats, CacheService.TIMEOUT_MEDIUM)
            logger.debug(f"Cached stats for user {user.id}")

        return stats

    @staticmethod
    def invalidate_user_stats(user):
        """Invalidate user statistics cache"""
        cache_key = CacheKeys.USER_STATS.format(user_id=user.id)
        cache.delete(cache_key)

        # Also invalidate related caches
        cache.delete(CacheKeys.USER_WRITING_STREAK.format(user_id=user.id))
        cache.delete(CacheKeys.USER_ENTRIES_COUNT.format(user_id=user.id))
        cache.delete(CacheKeys.USER_MOOD_DISTRIBUTION.format(user_id=user.id))

        logger.debug(f"Invalidated stats cache for user {user.id}")

    @staticmethod
    def get_marketplace_featured():
        """Get cached featured marketplace content"""
        featured = cache.get(CacheKeys.MARKETPLACE_FEATURED)

        if featured is None:
            from .models import Journal

            # Get featured content with optimized queries
            base_query = Journal.objects.filter(is_published=True).select_related('author')

            featured = {
                'staff_picks': list(base_query.filter(is_staff_pick=True)[:6]),
                'trending': list(base_query.order_by('-popularity_score')[:6]),
                'new_releases': list(base_query.order_by('-date_published')[:6]),
                'top_earning': list(base_query.order_by('-total_tips')[:6]),
                'popular_free': list(base_query.filter(price=0).order_by('-view_count')[:6])
            }

            cache.set(CacheKeys.MARKETPLACE_FEATURED, featured, CacheService.TIMEOUT_LONG)
            logger.debug("Cached marketplace featured content")

        return featured

    @staticmethod
    def get_marketplace_stats():
        """Get cached marketplace statistics"""
        stats = cache.get(CacheKeys.MARKETPLACE_STATS)

        if stats is None:
            from .models import Journal, JournalPurchase
            from django.contrib.auth.models import User

            # Calculate comprehensive marketplace stats
            journals = Journal.objects.filter(is_published=True)

            stats = {
                'total_journals': journals.count(),
                'total_authors': User.objects.filter(
                    journals__is_published=True
                ).distinct().count(),
                'total_revenue': journals.aggregate(
                    total=Sum('total_tips')
                )['total'] or 0,
                'avg_price': journals.filter(price__gt=0).aggregate(
                    avg=Avg('price')
                )['avg'] or 0,
                'free_journals': journals.filter(price=0).count(),
                'premium_journals': journals.filter(price__gt=0).count(),
                'total_sales': JournalPurchase.objects.count(),
                'total_views': journals.aggregate(
                    total=Sum('view_count')
                )['total'] or 0,
                'avg_rating': 4.5,  # You could calculate this from reviews
            }

            cache.set(CacheKeys.MARKETPLACE_STATS, stats, CacheService.TIMEOUT_LONG)
            logger.debug("Cached marketplace statistics")

        return stats

    @staticmethod
    def invalidate_marketplace_cache():
        """Invalidate marketplace related caches"""
        cache_keys = [
            CacheKeys.MARKETPLACE_FEATURED,
            CacheKeys.MARKETPLACE_STATS,
            CacheKeys.MARKETPLACE_TRENDING,
            CacheKeys.MARKETPLACE_NEW_RELEASES,
            CacheKeys.MARKETPLACE_TOP_EARNING,
            CacheKeys.MARKETPLACE_POPULAR_FREE,
            CacheKeys.POPULAR_TAGS,
        ]

        cache.delete_many(cache_keys)
        logger.debug("Invalidated marketplace caches")

    @staticmethod
    def get_journal_structure_cache_key(entry_ids, method='ai', journal_type='growth'):
        """Generate cache key for journal structure"""
        # Create a consistent hash from entry IDs and parameters
        entry_ids_str = ','.join(map(str, sorted(entry_ids)))
        cache_input = f"{entry_ids_str}_{method}_{journal_type}"
        entry_hash = hashlib.md5(cache_input.encode()).hexdigest()
        return CacheKeys.JOURNAL_STRUCTURE.format(hash=entry_hash)

    @staticmethod
    def get_compilation_analysis_cache_key(entry_ids):
        """Generate cache key for compilation analysis"""
        entry_ids_str = ','.join(map(str, sorted(entry_ids)))
        entry_hash = hashlib.md5(entry_ids_str.encode()).hexdigest()
        return CacheKeys.COMPILATION_ANALYSIS.format(hash=entry_hash)

    @staticmethod
    def get_popular_tags():
        """Get cached popular tags"""
        tags = cache.get(CacheKeys.POPULAR_TAGS)

        if tags is None:
            from .models import Tag, Entry

            # Get tags with usage counts
            tags = Tag.objects.annotate(
                usage_count=Count('entries')
            ).filter(usage_count__gt=0).order_by('-usage_count')[:20]

            # Convert to serializable format
            tags_data = [
                {
                    'name': tag.name,
                    'count': tag.usage_count,
                    'category': getattr(tag, 'category', 'other')
                }
                for tag in tags
            ]

            cache.set(CacheKeys.POPULAR_TAGS, tags_data, CacheService.TIMEOUT_VERY_LONG)
            logger.debug("Cached popular tags")

        return tags

    @staticmethod
    def get_user_dashboard(user):
        """Get cached dashboard data"""
        cache_key = CacheKeys.USER_DASHBOARD.format(user_id=user.id)
        dashboard_data = cache.get(cache_key)

        if dashboard_data is None:
            from .models import Entry, LifeChapter, Biography

            # Gather dashboard data
            dashboard_data = {
                'stats': CacheService.get_user_stats(user),
                'insights': CacheService.get_user_insights(user)[:3],  # Latest 3 insights
                'recent_entries': list(Entry.objects.filter(user=user).select_related(
                    'chapter'
                ).prefetch_related('tags')[:5]),
                'active_chapter': LifeChapter.objects.filter(
                    user=user, is_active=True
                ).first(),
                'biography_exists': Biography.objects.filter(user=user).exists(),
                'time_periods': CacheService._get_time_periods(user),
            }

            cache.set(cache_key, dashboard_data, CacheService.TIMEOUT_SHORT)
            logger.debug(f"Cached dashboard for user {user.id}")

        return dashboard_data

    @staticmethod
    def invalidate_user_dashboard(user):
        """Invalidate user dashboard cache"""
        cache_key = CacheKeys.USER_DASHBOARD.format(user_id=user.id)
        cache.delete(cache_key)
        logger.debug(f"Invalidated dashboard cache for user {user.id}")

    # Helper methods
    @staticmethod
    def _calculate_writing_streak(user):
        """Calculate writing streak (cached separately for performance)"""
        cache_key = CacheKeys.USER_WRITING_STREAK.format(user_id=user.id)
        streak = cache.get(cache_key)

        if streak is None:
            from .models import Entry

            # Get distinct entry dates for the user
            entry_dates = Entry.objects.filter(user=user).values_list(
                'created_at__date', flat=True
            ).distinct().order_by('-created_at__date')

            if not entry_dates:
                streak = 0
            else:
                today = timezone.now().date()
                yesterday = today - timedelta(days=1)

                # Check if user wrote today or yesterday
                if entry_dates[0] not in [today, yesterday]:
                    streak = 0
                else:
                    streak = 1
                    current_date = entry_dates[0]

                    # Count consecutive days
                    for entry_date in entry_dates[1:]:
                        expected_date = current_date - timedelta(days=1)
                        if entry_date == expected_date:
                            streak += 1
                            current_date = entry_date
                        else:
                            break

            cache.set(cache_key, streak, CacheService.TIMEOUT_SHORT)

        return streak

    @staticmethod
    def _get_most_used_mood(user):
        """Get user's most frequently used mood"""
        from .models import Entry
        from django.db.models import Count

        mood_data = Entry.objects.filter(
            user=user, mood__isnull=False
        ).values('mood').annotate(
            count=Count('mood')
        ).order_by('-count').first()

        return mood_data['mood'] if mood_data else None

    @staticmethod
    def _get_favorite_tags(user):
        """Get user's most frequently used tags"""
        from .models import Tag
        from django.db.models import Count

        tags = Tag.objects.filter(
            user=user
        ).annotate(
            usage_count=Count('entries')
        ).order_by('-usage_count')[:5]

        return [tag.name for tag in tags]

    @staticmethod
    def _get_time_periods(user):
        """Get time periods for user's entries"""
        from .models import Entry

        entries = Entry.objects.filter(user=user)
        time_periods = {}

        for entry in entries:
            period = entry.get_time_period()
            if period not in time_periods:
                time_periods[period] = {
                    'period': period,
                    'count': 0,
                    'first_entry': None
                }

            time_periods[period]['count'] += 1
            if (time_periods[period]['first_entry'] is None or
                entry.created_at < time_periods[period]['first_entry'].created_at):
                time_periods[period]['first_entry'] = entry

        return sorted(time_periods.values(), key=lambda x: x['period'], reverse=True)[:5]

# Signal handlers for cache invalidation
@receiver(post_save, sender='diary.Entry')
def invalidate_entry_caches(sender, instance, **kwargs):
    """Invalidate caches when entry is saved"""
    CacheService.invalidate_user_stats(instance.user)
    CacheService.invalidate_user_dashboard(instance.user)

    # Invalidate global stats if this affects them
    cache.delete(CacheKeys.GLOBAL_STATS)

@receiver(post_delete, sender='diary.Entry')
def invalidate_entry_delete_caches(sender, instance, **kwargs):
    """Invalidate caches when entry is deleted"""
    CacheService.invalidate_user_stats(instance.user)
    CacheService.invalidate_user_dashboard(instance.user)

@receiver(post_save, sender='diary.Journal')
def invalidate_journal_caches(sender, instance, **kwargs):
    """Invalidate caches when journal is saved"""
    if instance.is_published:
        CacheService.invalidate_marketplace_cache()

    # Invalidate author's published journals cache
    cache.delete(CacheKeys.user_published_journals(instance.author.id))

@receiver(post_save, sender='diary.UserInsight')
def invalidate_insight_caches(sender, instance, **kwargs):
    """Invalidate insight caches when insights are updated"""
    CacheService.invalidate_user_insights(instance.user)
    CacheService.invalidate_user_dashboard(instance.user)

@receiver(post_save, sender='diary.Tag')
def invalidate_tag_caches(sender, instance, **kwargs):
    """Invalidate tag caches when tags are updated"""
    cache.delete(CacheKeys.POPULAR_TAGS)
