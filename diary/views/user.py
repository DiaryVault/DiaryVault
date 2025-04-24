import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
from django.utils import timezone
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.db import IntegrityError
from datetime import timedelta

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from ..models import Entry, Tag, UserPreference, LifeChapter

logger = logging.getLogger(__name__)

@login_required
def account_settings(request):
    # Handle form submission
    if request.method == 'POST':
        # Get form data
        username = request.POST.get('username')
        email = request.POST.get('email')
        name = request.POST.get('name')

        # Update user information
        user = request.user

        # Only update if values changed
        if username and username != user.username:
            user.username = username

        if email and email != user.email:
            user.email = email

        # Handle name (split into first_name and last_name)
        if name:
            name_parts = name.split()
            if len(name_parts) > 0:
                user.first_name = name_parts[0]
                if len(name_parts) > 1:
                    user.last_name = ' '.join(name_parts[1:])

        user.save()

        messages.success(request, "Your account settings have been updated!")
        return redirect('account_settings')

    # Get basic statistics
    try:
        total_entries = Entry.objects.filter(user=request.user).count()
    except:
        total_entries = 0

    # Calculate join date
    join_date = request.user.date_joined

    # Simple placeholder for streak (you can implement proper streak calculation later)
    streak = 0
    longest_streak = 0

    # Try to get some basic streak information if Entry model exists
    try:
        # Count entries in the last 7 days as a simple "streak" placeholder
        recent_entries = Entry.objects.filter(
            user=request.user,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        streak = min(recent_entries, 7)  # Cap at 7 for now
        longest_streak = streak  # Simplified version
    except:
        pass

    return render(request, 'diary/account_settings.html', {
        'total_entries': total_entries,
        'join_date': join_date,
        'streak': streak,
        'longest_streak': longest_streak,
    })

@login_required
def preferences(request):
    """View for managing user preferences"""
    # Get or create user preferences
    user_prefs, created = UserPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Update preferences from form
        user_prefs.writing_style = request.POST.get('writing_style', 'reflective')
        user_prefs.tone = request.POST.get('tone', 'balanced')
        user_prefs.focus_areas = request.POST.get('focus_areas', '')
        user_prefs.language_complexity = request.POST.get('language_complexity', 'moderate')
        user_prefs.metaphor_frequency = request.POST.get('metaphor_frequency', 'occasional')
        user_prefs.include_questions = 'include_questions' in request.POST

        user_prefs.save()

        messages.success(request, "Your journal preferences have been updated!")
        return redirect('dashboard')

    # Prepare context for the template
    context = {
        'preferences': user_prefs,
        'page_title': 'Journal Preferences',
    }

    return render(request, 'diary/preferences.html', context)

def get_user_preferences(user):
    """Get user preferences or return defaults for anonymous users"""
    if not user or not user.is_authenticated:
        return {
            'writing_style': 'reflective',
            'tone': 'balanced',
            'focus_areas': [],
            'language_complexity': 'moderate',
            'include_questions': True,
            'metaphor_frequency': 'occasional'
        }

    try:
        prefs = UserPreference.objects.get(user=user)
        return {
            'writing_style': prefs.writing_style,
            'tone': prefs.tone,
            'focus_areas': prefs.get_focus_areas_list(),
            'language_complexity': prefs.language_complexity,
            'include_questions': prefs.include_questions,
            'metaphor_frequency': prefs.metaphor_frequency
        }
    except UserPreference.DoesNotExist:
        # Create default preferences
        prefs = UserPreference.objects.create(user=user)
        return {
            'writing_style': prefs.writing_style,
            'tone': prefs.tone,
            'focus_areas': [],
            'language_complexity': prefs.language_complexity,
            'include_questions': prefs.include_questions,
            'metaphor_frequency': prefs.metaphor_frequency
        }

@receiver(user_logged_in)
def save_pending_entry(sender, user, request, **kwargs):
    """Save any pending entry after user logs in"""
    if 'pending_entry' in request.session:
        entry_data = request.session.pop('pending_entry')

        try:
            # Create the entry
            entry = Entry.objects.create(
                user=user,
                title=entry_data.get('title', 'Untitled Entry'),
                content=entry_data.get('content', ''),
                mood=entry_data.get('mood')
            )

            # Add tags
            tags = entry_data.get('tags', [])
            if not tags and entry_data.get('content'):
                from ..utils.analytics import auto_generate_tags
                tags = auto_generate_tags(entry_data.get('content'), entry_data.get('mood'))

            if tags:
                for tag_name in tags:
                    tag_name = tag_name.lower().strip()
                    try:
                        tag, created = Tag.objects.get_or_create(
                            name=tag_name,
                            user=user
                        )
                    except IntegrityError:
                        # If there's an integrity error, try once more
                        tag = Tag.objects.get(name=tag_name, user=user)

                    entry.tags.add(tag)

            # Optional: generate summary
            try:
                from ..services.ai_service import AIService
                AIService.generate_entry_summary(entry)
            except Exception as e:
                logger.error(f"Failed to generate summary for pending entry: {str(e)}")

            # Set a flag to indicate entry was saved
            request.session['entry_saved'] = True
            request.session['saved_entry_id'] = entry.id

        except Exception as e:
            logger.error(f"Error creating entry after login: {str(e)}", exc_info=True)

def manage_chapters(request):
    # Get the active chapter
    active_chapter = None
    try:
        # Instead of get(), use filter() and get the most recent one
        active_chapters = LifeChapter.objects.filter(user=request.user, is_active=True).order_by('-start_date')
        if active_chapters.exists():
            active_chapter = active_chapters.first()
            # Add some statistics
            active_chapter.entry_count = Entry.objects.filter(chapter=active_chapter).count()
            active_chapter.duration_days = (timezone.now().date() - active_chapter.start_date).days + 1
            # You could add more stats here

            # Optionally, fix the data inconsistency by deactivating other active chapters
            if active_chapters.count() > 1:
                for chapter in active_chapters[1:]:
                    chapter.is_active = False
                    chapter.end_date = timezone.now().date()
                    chapter.save()
    except Exception as e:
        # Handle any other exceptions
        print(f"Error retrieving active chapter: {e}")

    # Get past chapters
    past_chapters = LifeChapter.objects.filter(
        user=request.user,
        is_active=False
    ).order_by('-end_date')

    # Add stats to past chapters
    for chapter in past_chapters:
        chapter.entry_count = Entry.objects.filter(chapter=chapter).count()
        if chapter.start_date and chapter.end_date:
            chapter.duration_days = (chapter.end_date - chapter.start_date).days + 1

    context = {
        'active_chapter': active_chapter,
        'past_chapters': past_chapters
    }
    return render(request, 'diary/chapters.html', context)


@login_required
@require_POST
def create_chapter(request):
    try:
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        color = request.POST.get('color', 'indigo')
        start_date = request.POST.get('start_date')

        if not start_date:
            start_date = timezone.now().date()

        # If there's an active chapter, close it first
        try:
            active_chapter = LifeChapter.objects.get(user=request.user, is_active=True)
            active_chapter.is_active = False
            active_chapter.end_date = timezone.now().date()
            active_chapter.save()
        except LifeChapter.DoesNotExist:
            pass

        # Create new chapter
        LifeChapter.objects.create(
            user=request.user,
            title=title,
            description=description,
            color=color,
            start_date=start_date,
            is_active=True
        )

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def update_chapter(request):
    try:
        chapter_id = request.POST.get('chapter_id')
        chapter = LifeChapter.objects.get(id=chapter_id, user=request.user)

        chapter.title = request.POST.get('title')
        chapter.description = request.POST.get('description', '')
        chapter.color = request.POST.get('color', chapter.color)

        # Handle active status
        is_active = request.POST.get('is_active') == 'on'

        # If making this chapter active, deactivate any currently active chapter
        if is_active and not chapter.is_active:
            try:
                active_chapter = LifeChapter.objects.get(user=request.user, is_active=True)
                active_chapter.is_active = False
                active_chapter.end_date = timezone.now().date()
                active_chapter.save()
            except LifeChapter.DoesNotExist:
                pass

            chapter.is_active = True
            chapter.end_date = None
        # If deactivating this chapter
        elif not is_active and chapter.is_active:
            chapter.is_active = False
            chapter.end_date = timezone.now().date()

        chapter.save()
        return JsonResponse({'success': True})
    except LifeChapter.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Chapter not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def close_chapter(request, chapter_id):
    try:
        chapter = LifeChapter.objects.get(id=chapter_id, user=request.user, is_active=True)
        chapter.is_active = False
        chapter.end_date = timezone.now().date()
        chapter.save()
        return JsonResponse({'success': True})
    except LifeChapter.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Active chapter not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def reactivate_chapter(request, chapter_id):
    try:
        # First deactivate any currently active chapter
        try:
            active_chapter = LifeChapter.objects.get(user=request.user, is_active=True)
            active_chapter.is_active = False
            active_chapter.end_date = timezone.now().date()
            active_chapter.save()
        except LifeChapter.DoesNotExist:
            pass

        # Now reactivate the requested chapter
        chapter = LifeChapter.objects.get(id=chapter_id, user=request.user, is_active=False)
        chapter.is_active = True
        chapter.end_date = None
        chapter.save()
        return JsonResponse({'success': True})
    except LifeChapter.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Chapter not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def delete_chapter(request, chapter_id):
    try:
        chapter = LifeChapter.objects.get(id=chapter_id, user=request.user)

        # Update any entries that were in this chapter
        Entry.objects.filter(chapter=chapter).update(chapter=None)

        # Delete the chapter
        chapter.delete()
        return JsonResponse({'success': True})
    except LifeChapter.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Chapter not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
