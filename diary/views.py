# Standard library imports
import json
import time
import hashlib
import logging
from datetime import datetime, timedelta
from collections import Counter
from functools import wraps

# Third-party imports
import requests
from requests.exceptions import Timeout, ConnectionError, RequestException

# Django imports
from django.db import IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.db.models import Count
from django.core.cache import cache
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.auth.views import LoginView
from django.contrib.auth import views as auth_views
from .models import Journal, JournalEntry
from django.contrib.auth.models import User

# Local app imports
from .models import (
    Entry, Tag, SummaryVersion, LifeChapter, Biography,
    UserInsight, EntryTag, UserPreference
)
from .forms import EntryForm, SignUpForm, LifeChapterForm
from .ai_services import AIService

def get_content_hash(journal_content):
    """Create a unique hash for the journal content to use as cache key"""
    return hashlib.md5(journal_content.encode('utf-8')).hexdigest()

logger = logging.getLogger(__name__)

def home(request):
    """Landing page for non-logged in users"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    return render(request, 'diary/home.html')

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            login(request, user)

            # Create default tags and chapters for new user
            default_tags = ['personal', 'work', 'goals', 'ideas', 'memories']
            for tag_name in default_tags:
                Tag.objects.create(name=tag_name, user=user)

            default_chapters = [
                {'title': 'Personal Growth', 'color': 'amber-600', 'description': 'Lessons learned and wisdom gained through challenges'},
                {'title': 'Career Journey', 'color': 'purple-700', 'description': 'Professional development and work experiences'},
            ]
            for chapter in default_chapters:
                LifeChapter.objects.create(user=user, **chapter)

            return redirect('dashboard')
    else:
        form = SignUpForm()

    return render(request, 'diary/signup.html', {'form': form})

@login_required
def dashboard(request):
    """Main dashboard with books and recent entries"""
    # Check for save_after_login flag
    if request.session.pop('save_after_login', False):
        try:
            # Try to get the entry data from localStorage via a hidden form submission
            # or create a new entry with minimal data
            entry = Entry.objects.create(
                user=request.user,
                title="Journal Entry",
                content="Entry created after login",
            )

            # Flash a message to the user
            messages.success(request, "Your journal entry was created successfully. Please edit it to add content.")

            # Redirect to the entry detail page
            return redirect('entry_detail', entry_id=entry.id)
        except Exception as e:
            logger.error(f"Error creating entry after login: {str(e)}")

    # Get time periods
    entries = Entry.objects.filter(user=request.user)
    time_periods = {}

    # Group entries by quarter/year
    for entry in entries:
        period = entry.get_time_period()
        if period not in time_periods:
            time_periods[period] = {
                'period': period,
                'count': 0,
                'entries': [],
                'first_entry': None,
                'color': 'sky-700'  # Default color
            }

        time_periods[period]['count'] += 1
        time_periods[period]['entries'].append(entry)

        # Keep track of first entry for preview
        if time_periods[period]['first_entry'] is None or entry.created_at < time_periods[period]['first_entry'].created_at:
            time_periods[period]['first_entry'] = entry

    # Assign different colors to time periods
    colors = ['sky-700', 'indigo-600', 'emerald-600', 'amber-600', 'rose-600']
    for i, period_key in enumerate(time_periods.keys()):
        time_periods[period_key]['color'] = colors[i % len(colors)]

    # Sort time periods by most recent first
    sorted_periods = sorted(time_periods.values(), key=lambda x: x['period'], reverse=True)

    # Get life chapters
    chapters = LifeChapter.objects.filter(user=request.user)

    # Get recent entries
    recent_entries = entries.order_by('-created_at')[:5]

    # Get biography
    biography = Biography.objects.filter(user=request.user).first()

    # Get insights
    insights = UserInsight.objects.filter(user=request.user)

    # Calculate streak
    streak = 0
    today = timezone.now().date()

    # Check entries for consecutive days
    for i in range(365):  # Check up to a year back
        check_date = today - timedelta(days=i)
        if entries.filter(created_at__date=check_date).exists():
            if i == 0 or streak > 0:  # Today or continuing streak
                streak += 1
            else:
                break  # Streak broken
        elif streak > 0:  # No entry for this day, streak ends
            break

    context = {
        'time_periods': sorted_periods[:5],  # Show top 5 most recent periods
        'chapters': chapters,
        'recent_entries': recent_entries,
        'biography': biography,
        'insights': insights,
        'streak': streak,
        'total_entries': entries.count(),
        'completion_percentage': biography.completion_percentage() if biography else 0
    }

    return render(request, 'diary/dashboard.html', context)

@login_required
def journal(request):
    """Create a new diary entry"""
    if request.method == 'POST':
        form = EntryForm(request.POST)
        if form.is_valid():
            # Save without committing to get the entry instance
            entry = form.save(commit=False)
            # Set the user manually
            entry.user = request.user
            # Now save to the database
            entry.save()

            # Generate AI summary
            AIService.generate_entry_summary(entry)

            messages.success(request, 'Entry saved successfully!')

            # If there are enough entries, regenerate insights
            entry_count = Entry.objects.filter(user=request.user).count()
            if entry_count % 5 == 0:  # Every 5 entries, update insights
                AIService.generate_insights(request.user)

            return redirect('entry_detail', entry_id=entry.id)
    else:
        form = EntryForm()

    return render(request, 'diary/journal.html', {'form': form})

@login_required
def entry_detail(request, entry_id):
    """View a single diary entry"""
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)

    if request.method == 'POST':
        if 'regenerate_summary' in request.POST:
            # Regenerate AI summary
            AIService.generate_entry_summary(entry)
            messages.success(request, 'Summary regenerated!')
            return redirect('entry_detail', entry_id=entry.id)

        elif 'restore_version' in request.POST:
            version_id = request.POST.get('version_id')
            version = get_object_or_404(SummaryVersion, id=version_id, entry=entry)

            # Store current summary as a version
            if entry.summary:
                SummaryVersion.objects.create(
                    entry=entry,
                    summary=entry.summary
                )

            # Restore old version
            entry.summary = version.summary
            entry.save()

            messages.success(request, 'Summary version restored!')
            return redirect('entry_detail', entry_id=entry.id)

    # Get related entries (same tags)
    related_entries = Entry.objects.filter(
        user=request.user,
        tags__in=entry.tags.all()
    ).exclude(id=entry.id).distinct()[:3]

    context = {
        'entry': entry,
        'summary_versions': entry.versions.all(),
        'related_entries': related_entries,
    }

    return render(request, 'diary/entry_detail.html', context)

@login_required
def biography(request):
    """View and generate biography"""
    biography = Biography.objects.filter(user=request.user).first()
    entry_count = Entry.objects.filter(user=request.user).count()

    # Get chapters
    chapters = LifeChapter.objects.filter(user=request.user)

    # Determine date range for entries
    first_entry = Entry.objects.filter(user=request.user).order_by('created_at').first()
    last_entry = Entry.objects.filter(user=request.user).order_by('-created_at').first()

    date_range = "No entries yet"
    if first_entry and last_entry:
        if first_entry.created_at.year == last_entry.created_at.year:
            date_range = f"{first_entry.created_at.strftime('%B %Y')}"
        else:
            date_range = f"{first_entry.created_at.strftime('%B %Y')} to {last_entry.created_at.strftime('%B %Y')}"

    # Initialize chapter contents
    chapter_contents = {}

    # Handle regenerate request
    if request.method == 'POST':
        if 'regenerate_biography' in request.POST:
            try:
                # Generate or regenerate the main biography
                AIService.generate_user_biography(request.user)
                messages.success(request, 'Biography generated successfully!')
            except Exception as e:
                logger.error(f"Error generating biography: {str(e)}", exc_info=True)
                messages.error(request, 'Failed to generate biography. Please try again later.')

            return redirect('biography')

        elif 'regenerate_chapter' in request.POST:
            chapter = request.POST.get('chapter')
            if chapter:
                try:
                    # Generate or regenerate a specific chapter
                    AIService.generate_user_biography(request.user, chapter=chapter)
                    messages.success(request, f'Chapter "{chapter}" generated successfully!')
                except Exception as e:
                    logger.error(f"Error generating chapter {chapter}: {str(e)}", exc_info=True)
                    messages.error(request, f'Failed to generate chapter "{chapter}". Please try again later.')

                return redirect('biography')

    # Get chapter contents if biography exists
    if biography and biography.chapters_data:
        # Debug what's actually in chapters_data
        print("CHAPTERS DATA:", biography.chapters_data)

        # Create a normalized mapping (convert to lowercase with underscores)
        for chapter in chapters:
            chapter_key = chapter.title.lower().replace(' ', '_')
            if chapter_key in biography.chapters_data:
                chapter_contents[chapter.title] = biography.chapters_data[chapter_key]['content']

        # Also check for standard chapters that might not be in your LifeChapter model
        standard_chapters = {
            'childhood': 'Childhood',
            'education': 'Education',
            'career': 'Career Journey',
            'relationships': 'Relationships',
            'personal_growth': 'Personal Growth',
            'recent_years': 'Recent Years'
        }

        for key, title in standard_chapters.items():
            if key in biography.chapters_data and key not in chapter_contents:
                chapter_contents[title] = biography.chapters_data[key]['content']

    context = {
        'biography': biography.content if biography else '',
        'biography_obj': biography,
        'chapters': chapters,
        'chapter_contents': chapter_contents,
        'entry_count': entry_count,
        'date_range': date_range,
        'childhood_content': chapter_contents.get('Childhood', ''),
        'education_content': chapter_contents.get('Education', ''),
        'career_content': chapter_contents.get('Career Journey', ''),
        'relationships_content': chapter_contents.get('Relationships', ''),
        'personal_growth_content': chapter_contents.get('Personal Growth', ''),
        'recent_years_content': chapter_contents.get('Recent Years', '')
    }

    return render(request, 'diary/biography.html', context)

@login_required
def insights(request):
    """View for showing AI-generated insights about the user's journal entries."""

    # Handle regenerating insights
    if request.method == 'POST' and 'regenerate_insights' in request.POST:
        # Delete existing insights for this user
        UserInsight.objects.filter(user=request.user).delete()

        # Generate new insights (this would normally call your AI service)
        generate_user_insights(request.user)

        messages.success(request, "Insights regenerated!")
        return redirect('insights')

    # Get this user's insights from the database
    user_insights = UserInsight.objects.filter(user=request.user)

    # Prepare data structures
    mood_analysis = None
    patterns = []
    suggestions = []

    # Process insights by type
    for insight in user_insights:
        if insight.insight_type == 'mood_analysis':
            mood_analysis = insight
        elif insight.insight_type == 'pattern':
            patterns.append(insight)
        elif insight.insight_type == 'suggestion':
            suggestions.append(insight)

    # Get all user entries
    entries = Entry.objects.filter(user=request.user)

    # Generate mood distribution data
    mood_distribution = generate_mood_distribution(entries)

    # Generate tag distribution data
    tag_distribution = generate_tag_distribution(entries)

    # Generate time-based mood trend data for the chart
    mood_trends = generate_mood_trends(entries)

    context = {
        'mood_analysis': mood_analysis,
        'patterns': patterns,
        'suggestions': suggestions,
        'mood_distribution': mood_distribution,
        'tag_distribution': tag_distribution,
        'mood_trends': mood_trends,
    }

    return render(request, 'diary/insights.html', context)

def generate_mood_distribution(entries):
    """
    Analyze entries to extract mood distribution data.
    Returns a list of mood objects with name and percentage.
    """
    # Skip if no entries
    if not entries:
        return []

    # Extract moods from entries
    moods = []
    for entry in entries:
        # Use entry's mood field
        if entry.mood:
            moods.append(entry.mood)

    # Count occurrences of each mood
    mood_counts = Counter(moods)

    # Skip if no moods found
    if not mood_counts:
        return []

    # Calculate percentages
    total_moods = sum(mood_counts.values())
    mood_distribution = [
        {
            'name': mood,
            'count': count,
            'percentage': round((count / total_moods) * 100),
            # Add appropriate emoji for each mood
            'emoji': get_mood_emoji(mood)
        }
        for mood, count in mood_counts.most_common()
    ]

    return mood_distribution

def generate_tag_distribution(entries):
    """
    Analyze entries to extract tag distribution data.
    Returns a list of tag objects with name and percentage.
    """
    # Skip if no entries
    if not entries:
        return []

    # Get all tags used in these entries using ManyToMany through relationship
    tags = Tag.objects.filter(entries__in=entries).values('name').annotate(
        count=Count('name')
    ).order_by('-count')

    # Skip if no tags
    if not tags:
        return []

    # Calculate total and percentages
    total_tags = sum(tag['count'] for tag in tags)

    tag_distribution = [
        {
            'name': tag['name'],
            'count': tag['count'],
            'percentage': round((tag['count'] / total_tags) * 100),
            'color': get_tag_color(tag['name'])  # Generate consistent color for tag
        }
        for tag in tags
    ]

    return tag_distribution

def generate_mood_trends(entries):
    """
    Generate time-series data for mood trends over the past 30 days.
    Returns data suitable for a chart visualization.
    """
    # Skip if no entries
    if not entries:
        return []

    # Get entries from the last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_entries = entries.filter(created_at__gte=thirty_days_ago).order_by('created_at')

    # Skip if no recent entries
    if not recent_entries:
        return []

    # Extract date and mood data
    trends_data = []
    for entry in recent_entries:
        date_str = entry.created_at.strftime('%Y-%m-%d')

        # Get mood value
        mood_value = 5  # Default neutral value

        if entry.mood:
            # Convert mood string to numeric value for chart
            mood_value = mood_to_numeric_value(entry.mood)

        trends_data.append({
            'date': date_str,
            'mood': mood_value
        })

    return trends_data

def get_mood_emoji(mood):
    """Return appropriate emoji for a given mood."""
    mood = mood.lower()
    emoji_map = {
        'happy': '😊',
        'sad': '😢',
        'angry': '😡',
        'excited': '😃',
        'content': '😌',
        'anxious': '😰',
        'stressed': '😖',
        'relaxed': '😎',
        'proud': '🥳',
        'motivated': '💪',
        'grateful': '🙏',
        'hopeful': '✨'
        # Add more as needed
    }
    return emoji_map.get(mood, '😐')  # Default neutral emoji

def get_tag_color(tag_name):
    """
    Generate a consistent color for a tag based on its name.
    This ensures the same tag always gets the same color.
    """
    # Simple hash function to generate a number from the tag name
    tag_hash = sum(ord(c) for c in tag_name)

    # List of pleasant colors to choose from
    colors = [
        'indigo-600', 'blue-500', 'sky-500', 'cyan-500', 'teal-500',
        'emerald-500', 'green-500', 'lime-500', 'yellow-500', 'amber-500',
        'orange-500', 'red-500', 'rose-500', 'fuchsia-500', 'purple-500',
        'violet-500'
    ]

    # Use the hash to select a color
    color_index = tag_hash % len(colors)
    return colors[color_index]

def mood_to_numeric_value(mood):
    """Convert mood tag to numeric value for charting (1-10 scale)."""
    mood = mood.lower()
    mood_values = {
        'very sad': 1,
        'sad': 2,
        'disappointed': 3,
        'anxious': 4,
        'neutral': 5,
        'calm': 6,
        'content': 7,
        'happy': 8,
        'excited': 9,
        'ecstatic': 10
        # Add more as needed
    }
    return mood_values.get(mood, 5)  # Default to neutral (5)

def generate_user_insights(user):
    """
    Generate insights for a user - this is where you would call your AI service.
    For now, we'll create placeholder insights for demonstration.
    """
    # Create a mood analysis insight
    UserInsight.objects.create(
        user=user,
        insight_type='mood_analysis',
        title='Mood Analysis',
        content='The overall mood of the entries is positive and triumphant, with a sense of accomplishment and pride. The tone is reflective and celebratory, indicating a period of personal growth and success.'
    )

    # Create pattern insights
    patterns = [
        {
            'title': 'Newfound Confidence',
            'content': 'Your recent entries show increased confidence in approaching challenges. You\'ve been using more assertive language and focusing on capabilities rather than limitations.'
        },
        {
            'title': 'Focus on Achievement',
            'content': 'There\'s a strong theme of goal attainment in your writing. You frequently mention completing tasks and setting new objectives.'
        }
    ]

    for pattern in patterns:
        UserInsight.objects.create(
            user=user,
            insight_type='pattern',
            title=pattern['title'],
            content=pattern['content']
        )

    # Create suggestion insights
    suggestions = [
        {
            'title': 'Building on Momentum',
            'content': 'Consider creating a "wins" section in your journal to track accomplishments, both big and small. This can help maintain motivation when facing new challenges.'
        },
        {
            'title': 'Reflecting on Motivations',
            'content': 'Your entries focus on what you\'ve achieved, but less on why. Try exploring what drives your accomplishments to better understand your core motivations.'
        }
    ]

    for suggestion in suggestions:
        UserInsight.objects.create(
            user=user,
            insight_type='suggestion',
            title=suggestion['title'],
            content=suggestion['content']
        )

@login_required
def edit_entry(request, entry_id):
    """Edit an existing entry using the same template as new entries"""
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)

    if request.method == 'POST':
        form = EntryForm(request.POST, instance=entry, user=request.user)  # Pass user here
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, "Entry updated successfully!")
            return redirect('entry_detail', entry_id=entry.id)
    else:
        form = EntryForm(instance=entry, user=request.user)  # And here

    # Use the same template as new entries but with different context
    context = {
        'form': form,
        'entry': entry,
        'is_edit_mode': True,
        'today': timezone.now()
    }

    return render(request, 'diary/journal.html', context)



@login_required
def delete_entry(request, entry_id):
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)
    return render(request, 'diary/delete_entry.html', {'entry': entry})

@login_required
def manage_chapters(request):
    chapters = LifeChapter.objects.filter(user=request.user)
    return render(request, 'diary/manage_chapters.html', {'chapters': chapters})

@login_required
def edit_chapter(request, chapter_id):
    chapter = get_object_or_404(LifeChapter, id=chapter_id, user=request.user)
    return render(request, 'diary/edit_chapter.html', {'chapter': chapter})

@login_required
def delete_chapter(request, chapter_id):
    chapter = get_object_or_404(LifeChapter, id=chapter_id, user=request.user)
    return render(request, 'diary/delete_chapter.html', {'chapter': chapter})

@login_required
def assign_to_chapter(request, entry_id):
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)
    chapters = LifeChapter.objects.filter(user=request.user)
    return render(request, 'diary/assign_to_chapter.html', {'entry': entry, 'chapters': chapters})

@login_required
def regenerate_summary_ajax(request, entry_id):
    """AJAX view to regenerate an entry summary"""
    if request.method == 'POST':
        entry = get_object_or_404(Entry, id=entry_id, user=request.user)
        summary = AIService.generate_entry_summary(entry)
        return JsonResponse({'success': True, 'summary': summary})
    return JsonResponse({'success': False, 'error': 'Invalid request'})


# Updated library view function for views.py

@login_required
def library(request):
    """Library view with tabs for different ways to browse entries"""
    # Get user entries - base queryset
    all_entries = Entry.objects.filter(user=request.user).order_by('-created_at')

    # Default to showing all entries
    entries = all_entries
    active_tab = 'time-periods'  # Default tab to match your existing HTML
    active_filter = None

    # Check for filter parameters
    tag_filter = request.GET.get('tag')
    mood_filter = request.GET.get('mood')
    chapter_filter = request.GET.get('chapter')

    # Apply filters based on GET parameters
    if tag_filter:
        entries = all_entries.filter(tags__name=tag_filter)
        active_tab = 'tags'
        active_filter = tag_filter
        # Get tagged entries specifically for the tag tab
        tagged_entries = entries
    elif mood_filter:
        entries = all_entries.filter(mood=mood_filter)
        active_tab = 'moods'
        active_filter = mood_filter
        # Get mood entries specifically for the mood tab
        mood_entries = entries
    elif chapter_filter:
        # Assuming you have a model relationship between Entry and LifeChapter
        chapter = get_object_or_404(LifeChapter, id=chapter_filter, user=request.user)
        entries = all_entries.filter(chapter=chapter)
        active_tab = 'time-periods'  # Show in the time periods tab with the chapter books
        active_filter = chapter.title

    # Get time periods (same code as before)
    time_periods = {}
    # Group entries by quarter/year
    for entry in all_entries:  # Use all_entries to show all time periods
        period = entry.get_time_period()
        if period not in time_periods:
            time_periods[period] = {
                'period': period,
                'count': 0,
                'entries': [],
                'first_entry': None,
                'color': 'sky-700'  # Default color
            }

        time_periods[period]['count'] += 1
        time_periods[period]['entries'].append(entry)

        # Keep track of first entry for preview
        if time_periods[period]['first_entry'] is None or entry.created_at < time_periods[period]['first_entry'].created_at:
            time_periods[period]['first_entry'] = entry

    # Assign different colors to time periods
    colors = ['sky-700', 'indigo-600', 'emerald-600', 'amber-600', 'rose-600']
    for i, period_key in enumerate(time_periods.keys()):
        time_periods[period_key]['color'] = colors[i % len(colors)]

    # Sort time periods by most recent first
    sorted_periods = sorted(time_periods.values(), key=lambda x: x['period'], reverse=True)

    # Get tags with counts from all entries
    tags = []
    for tag in Tag.objects.filter(user=request.user):
        count = all_entries.filter(tags=tag).count()
        if count > 0:
            tags.append({
                'id': tag.id,
                'name': tag.name,
                'count': count,
                'active': tag.name == tag_filter  # Mark as active if it's the current filter
            })

    # Sort tags by count
    tags.sort(key=lambda x: x['count'], reverse=True)

    # Get moods with counts
    moods = []
    mood_counts = {}
    for entry in all_entries:  # Use all_entries to show all moods
        if entry.mood:
            if entry.mood not in mood_counts:
                mood_counts[entry.mood] = {
                    'name': entry.mood,
                    'count': 0,
                    'emoji': get_mood_emoji(entry.mood),  # Use your emoji function
                    'active': entry.mood == mood_filter  # Mark as active if it's the current filter
                }
            mood_counts[entry.mood]['count'] += 1

    moods = list(mood_counts.values())
    moods.sort(key=lambda x: x['count'], reverse=True)

    # Get chapters with counts
    chapters = []
    for chapter in LifeChapter.objects.filter(user=request.user):
        # Count entries in this chapter - adjust the query based on your relationship
        count = all_entries.filter(chapter=chapter).count()
        chapters.append({
            'id': chapter.id,
            'title': chapter.title,
            'description': chapter.description,
            'count': count,
            'color': chapter.color,
            'active': str(chapter.id) == chapter_filter  # Mark as active if it's the current filter
        })

    # If no specific entries are filtered, use all entries for the respective tabs
    if not tag_filter:
        tagged_entries = all_entries
    if not mood_filter:
        mood_entries = all_entries

    context = {
        'time_periods': sorted_periods,
        'tags': tags,
        'moods': moods,
        'chapters': chapters,
        'entries': entries,  # These are the entries filtered by the active parameter
        'tagged_entries': tagged_entries if 'tagged_entries' in locals() else all_entries,
        'mood_entries': mood_entries if 'mood_entries' in locals() else all_entries,
        'total_entries': all_entries.count(),
        'filtered_count': entries.count(),
        'active_tab': active_tab,
        'active_filter': active_filter
    }

    return render(request, 'diary/library.html', context)

@login_required
def time_period_view(request, period):
    """View entries for a specific time period"""
    entries = Entry.objects.filter(
        user=request.user
    ).order_by('-created_at')

    # Filter to just this period
    period_entries = [entry for entry in entries if entry.get_time_period() == period]

    return render(request, 'diary/time_period.html', {
        'period': period,
        'entries': period_entries,
        'total_entries': len(period_entries)
    })

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

    # Get basic statistics (without requiring additional models or functions)
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta

    # Get total entries (if you have an Entry model)
    try:
        from .models import Entry
        total_entries = Entry.objects.filter(user=request.user).count()
    except (ImportError, AttributeError):
        total_entries = 0

    # Calculate join date
    join_date = request.user.date_joined

    # Simple placeholder for streak (you can implement proper streak calculation later)
    streak = 0
    longest_streak = 0

    # Try to get some basic streak information if Entry model exists
    try:
        from .models import Entry
        # Count entries in the last 7 days as a simple "streak" placeholder
        recent_entries = Entry.objects.filter(
            user=request.user,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        streak = min(recent_entries, 7)  # Cap at 7 for now
        longest_streak = streak  # Simplified version
    except (ImportError, AttributeError):
        pass

    return render(request, 'diary/account_settings.html', {
        'total_entries': total_entries,
        'join_date': join_date,
        'streak': streak,
        'longest_streak': longest_streak,
    })


def retry_on_failure(max_retries=3, delay=1, backoff=2, exceptions=(RequestException,)):
    """
    Retry decorator with exponential backoff for API calls
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = max_retries, delay
            while mtries > 0:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    msg = f"{func.__name__} failed. Retrying in {mdelay}s. Error: {str(e)}"
                    logger.warning(msg)

                    mtries -= 1
                    if mtries == 0:
                        logger.error(f"All retries failed for {func.__name__}: {str(e)}")
                        raise

                    time.sleep(mdelay)
                    mdelay *= backoff
        return wrapper
    return decorator

@retry_on_failure(max_retries=3, delay=1, backoff=2)
def call_grok_api(journal_content, timeout=10):
    """
    Call the Grok API with retries, timeouts and better error handling
    """
    request_id = int(time.time() * 1000)  # Simple request ID for tracking
    logger.info(f"API Request {request_id} started for content of length {len(journal_content)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.GROK_API_KEY}',
            'X-Request-ID': str(request_id)  # Add request ID for tracking
        }

        today = datetime.now().strftime("%B %d, %Y")  # Get current date
        prompt = f"""
        Transform the following daily activities into a reflective, well-written journal entry.
        Add emotional depth, insights, and reflection while staying true to the events mentioned.

        Today's date: {today}  # Include today's date explicitly

        User's activities: {journal_content}

        Write the entry in first person as if the user wrote it themselves, with a thoughtful, introspective tone.
        Include paragraphs for readability and natural flow.
        """

        payload = {
            'model': 'llama3-70b-8192',
            'messages': [
                {'role': 'system', 'content': 'You are a helpful journal assistant that transforms brief notes into thoughtful diary entries.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 800
        }

        # Add proper timeout to prevent hanging requests
        start_time = time.time()
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=timeout  # Add timeout
        )
        api_time = time.time() - start_time

        # Log response time for performance monitoring
        logger.info(f"API Request {request_id} completed in {api_time:.2f}s with status {response.status_code}")

        if response.status_code != 200:
            logger.error(f"API Request {request_id} failed: {response.status_code} - {response.text}")
            raise RequestException(f"API returned status code {response.status_code}: {response.text}")

        response_data = response.json()

        # Validate response structure
        if 'choices' not in response_data or not response_data['choices']:
            error_msg = f"Invalid API response structure: {response_data}"
            logger.error(f"API Request {request_id}: {error_msg}")
            raise ValueError(error_msg)

        # Extract the message content based on the API response structure
        return response_data['choices'][0]['message']['content']

    except Timeout:
        logger.error(f"API Request {request_id} timed out after {timeout}s")
        raise Timeout(f"Request timed out after {timeout} seconds")
    except ConnectionError as e:
        logger.error(f"API Request {request_id} connection error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"API Request {request_id} unexpected error: {str(e)}", exc_info=True)
        raise

@retry_on_failure(max_retries=2, delay=1, backoff=2)
def generate_title(journal_entry, timeout=5):
    """
    Generate a title for the journal entry with improved error handling
    """
    request_id = int(time.time() * 1000)
    logger.info(f"Title generation {request_id} started for entry of length {len(journal_entry)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.GROK_API_KEY}',
            'X-Request-ID': str(request_id)
        }

        prompt = f"""
        Create a short, engaging title for this journal entry:

        {journal_entry[:300]}...

        The title should be 5-7 words maximum, reflecting the main themes or feelings in the entry.
        """

        payload = {
            'model': 'llama3-70b-8192',  # Use the same model as the main function
            'messages': [
                {'role': 'system', 'content': 'You are a helpful writing assistant.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 30
        }

        start_time = time.time()
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=timeout
        )
        api_time = time.time() - start_time

        logger.info(f"Title generation {request_id} completed in {api_time:.2f}s with status {response.status_code}")

        if response.status_code != 200:
            logger.error(f"Title generation {request_id} failed: {response.status_code} - {response.text}")
            raise RequestException(f"API returned status code {response.status_code}")

        response_data = response.json()

        # Validate response structure with detailed error
        if 'choices' not in response_data:
            error_msg = f"Missing 'choices' in API response: {response_data}"
            logger.error(f"Title generation {request_id}: {error_msg}")
            raise ValueError(error_msg)

        if not response_data['choices'] or 'message' not in response_data['choices'][0]:
            error_msg = f"Invalid structure in API response: {response_data}"
            logger.error(f"Title generation {request_id}: {error_msg}")
            raise ValueError(error_msg)

        title = response_data['choices'][0]['message']['content'].strip('"').strip()

        # Add today's date to the title
        today = datetime.now().strftime("%B %d, %Y")
        return f"{title} - {today}"

    except Exception as e:
        logger.error(f"Title generation {request_id} error: {str(e)}", exc_info=True)
        # More descriptive fallback title
        today = datetime.now().strftime("%B %d, %Y")
        words = journal_entry.split()[:5]
        if words:
            # Create a title from the first few words
            return f"{' '.join(words)}... - {today}"
        return f"Journal Entry - {today}"

def generate_ai_content(journal_content):
    """
    Generate both journal entry and title with comprehensive error handling
    """
    try:
        # Start tracking performance
        start_time = time.time()

        # Generate the journal entry
        journal_entry = call_grok_api(journal_content)
        journal_time = time.time() - start_time

        # Then generate a title based on the entry
        title_start = time.time()
        title = generate_title(journal_entry)
        title_time = time.time() - title_start

        total_time = time.time() - start_time

        # Log performance metrics
        logger.info(f"Content generation completed - Entry: {journal_time:.2f}s, Title: {title_time:.2f}s, Total: {total_time:.2f}s")

        return {
            'title': title,
            'entry': journal_entry,
            'generation_time': round(total_time, 2)
        }
    except Exception as e:
        logger.error(f"Error in generate_ai_content: {str(e)}", exc_info=True)
        # Return fallback content
        today = datetime.now().strftime("%B %d, %Y")
        return {
            'title': f"Journal Entry - {today}",
            'entry': f"Today I {journal_content[:50]}..." if len(journal_content) > 50 else f"Today I {journal_content}...",
            'error': str(e)
        }

@require_POST
@csrf_exempt
def demo_journal(request):
    request_id = int(time.time() * 1000)
    logger.info(f"Journal request {request_id} started")

    try:
        start_time = time.time()

        data = json.loads(request.body)
        journal_content = data.get('journal_content', '')
        # Check if personalization is requested
        personalize = data.get('personalize', False)

        if not journal_content:
            logger.warning(f"Journal request {request_id}: No content provided")
            return JsonResponse({'error': 'No content provided'}, status=400)

        # If personalization is requested and user is logged in, use that
        if personalize and request.user.is_authenticated:
            # Create a unique cache key based on content and user
            user_id = request.user.id
            cache_key = f"journal_entry:user{user_id}:{get_content_hash(journal_content)}"
        else:
            # Otherwise use standard cache key
            cache_key = f"journal_entry:{get_content_hash(journal_content)}"

        # Try to get cached response
        cached_response = cache.get(cache_key)
        if cached_response:
            logger.info(f"Journal request {request_id} served from cache")
            cached_response['cache_hit'] = True
            cached_response['cache_type'] = 'server'
            cached_response['response_time'] = round(time.time() - start_time, 3)
            return JsonResponse(cached_response)

        # Generate new content if not cached
        if personalize and request.user.is_authenticated:
            # Use personalized generation
            response_data = generate_ai_content_personalized(journal_content, request.user)
        else:
            # Use standard generation
            response_data = generate_ai_content(journal_content)

        # Add metadata
        response_data['cache_hit'] = False
        response_data['cache_type'] = 'none'
        response_data['request_time'] = round(time.time() - start_time, 2)

        # Cache the response (only if successful and no errors)
        if 'error' not in response_data:
            cache.set(cache_key, response_data, timeout=3600)  # Cache for 1 hour

        logger.info(f"Journal request {request_id} completed in {response_data['request_time']}s")
        return JsonResponse(response_data)

    except json.JSONDecodeError:
        logger.error(f"Journal request {request_id}: Invalid JSON in request")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Journal request {request_id} failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Server error processing your request',
            'error_details': str(e),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, status=500)

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

def call_grok_api_personalized(journal_content, user_preferences):
    """
    Call the Grok API with personalized parameters based on user preferences
    """
    request_id = int(time.time() * 1000)
    logger.info(f"Personalized API Request {request_id} started for content length {len(journal_content)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.GROK_API_KEY}',
            'X-Request-ID': str(request_id)
        }

        # Build a personalized prompt based on preferences
        style_guide = ""

        # Writing style
        if user_preferences['writing_style'] == 'reflective':
            style_guide += "Write in a thoughtful, introspective tone with personal insights. "
        elif user_preferences['writing_style'] == 'analytical':
            style_guide += "Write in a logical, analytical tone with observations about patterns and causes. "
        elif user_preferences['writing_style'] == 'creative':
            style_guide += "Write in a creative, expressive tone with vivid descriptions and imagery. "
        elif user_preferences['writing_style'] == 'concise':
            style_guide += "Write concisely and to the point, focusing on key events and feelings. "
        elif user_preferences['writing_style'] == 'detailed':
            style_guide += "Include rich details and thorough descriptions of events, feelings, and surroundings. "
        elif user_preferences['writing_style'] == 'poetic':
            style_guide += "Include poetic language, metaphors, and a flowing, rhythmic writing style. "
        elif user_preferences['writing_style'] == 'humorous':
            style_guide += "Incorporate gentle humor and a lighthearted tone where appropriate. "

        # Emotional tone
        if user_preferences['tone'] == 'positive':
            style_guide += "Emphasize positive aspects and silver linings in events. "
        elif user_preferences['tone'] == 'balanced':
            style_guide += "Balance both positive and challenging aspects of experiences. "
        elif user_preferences['tone'] == 'realistic':
            style_guide += "Take a realistic, pragmatic approach to describing events. "
        elif user_preferences['tone'] == 'growth':
            style_guide += "Focus on lessons learned and personal growth opportunities. "

        # Focus areas
        if user_preferences['focus_areas']:
            areas = ', '.join(user_preferences['focus_areas'])
            style_guide += f"When relevant, emphasize these areas: {areas}. "

        # Language complexity
        if user_preferences['language_complexity'] == 'simple':
            style_guide += "Use simple, clear language avoiding complex vocabulary. "
        elif user_preferences['language_complexity'] == 'moderate':
            style_guide += "Use moderately sophisticated language accessible to most readers. "
        elif user_preferences['language_complexity'] == 'advanced':
            style_guide += "Use rich, sophisticated vocabulary and complex sentence structures. "

        # Metaphor frequency
        if user_preferences['metaphor_frequency'] == 'minimal':
            style_guide += "Use metaphors and analogies sparingly. "
        elif user_preferences['metaphor_frequency'] == 'occasional':
            style_guide += "Occasionally include metaphors or analogies to illustrate points. "
        elif user_preferences['metaphor_frequency'] == 'frequent':
            style_guide += "Frequently incorporate metaphors and analogies throughout the entry. "

        # Questions
        if user_preferences['include_questions']:
            style_guide += "End with 1-2 thoughtful reflective questions related to the events. "

        # Build the prompt with style guide

        today = datetime.now().strftime("%B %d, %Y")
        prompt = f"""
        Transform the following daily activities into a reflective, well-written journal entry.
        Add emotional depth, insights, and reflection while staying true to the events mentioned.

        User's activities: {journal_content}

        Style guide: {style_guide}

        Write the entry in first person as if the user wrote it themselves.
        Include paragraphs for readability and natural flow.
        """

        payload = {
            'model': 'llama3-70b-8192',
            'messages': [
                {'role': 'system', 'content': 'You are a helpful journal assistant that transforms brief notes into thoughtful diary entries.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 800
        }

        # Add proper timeout to prevent hanging requests
        start_time = time.time()
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=10
        )
        api_time = time.time() - start_time

        logger.info(f"API Request {request_id} completed in {api_time:.2f}s with status {response.status_code}")

        if response.status_code != 200:
            logger.error(f"API Request {request_id} failed: {response.status_code} - {response.text}")
            raise RequestException(f"API returned status code {response.status_code}")

        response_data = response.json()

        # Validate response structure
        if 'choices' not in response_data or not response_data['choices']:
            error_msg = f"Invalid API response structure: {response_data}"
            logger.error(f"API Request {request_id}: {error_msg}")
            raise ValueError(error_msg)

        return response_data['choices'][0]['message']['content']

    except Exception as e:
        logger.error(f"API Request {request_id} error: {str(e)}", exc_info=True)
        raise


def generate_ai_content_personalized(journal_content, user=None):
    """
    Generate both journal entry and title with personalization
    """
    try:
        # Get user preferences
        preferences = get_user_preferences(user)

        # Start tracking performance
        start_time = time.time()

        # Generate the journal entry with personalization
        journal_entry = call_grok_api_personalized(journal_content, preferences)
        journal_time = time.time() - start_time

        # Then generate a title based on the entry
        title_start = time.time()
        title = generate_title(journal_entry)
        title_time = time.time() - title_start

        total_time = time.time() - start_time

        # Log performance metrics
        logger.info(f"Personalized content generation completed - Entry: {journal_time:.2f}s, Title: {title_time:.2f}s, Total: {total_time:.2f}s")

        return {
            'title': title,
            'entry': journal_entry,
            'generation_time': round(total_time, 2),
            'personalized': True,
            'preferences_used': preferences
        }
    except Exception as e:
        logger.error(f"Error in personalized content generation: {str(e)}", exc_info=True)
        # Fallback to non-personalized version
        try:
            return generate_ai_content(journal_content)
        except Exception as inner_e:
            logger.error(f"Fallback content generation also failed: {str(inner_e)}", exc_info=True)
            # Final fallback
            today = datetime.now().strftime("%B %d, %Y")
            return {
                'title': f"Journal Entry - {today}",
                'entry': f"Today I {journal_content[:50]}..." if len(journal_content) > 50 else f"Today I {journal_content}...",
                'error': str(e),
                'personalized': False
            }

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

    return render(request, 'preferences.html', context)

def auto_generate_tags(content, mood=None):
    """Generate tags based on entry content and mood"""
    tags = set()

    # Common topics to check for
    topic_keywords = {
        'work': ['work', 'job', 'career', 'office', 'meeting', 'project', 'boss', 'colleague'],
        'family': ['family', 'parents', 'mom', 'dad', 'children', 'kids', 'brother', 'sister'],
        'health': ['health', 'workout', 'exercise', 'doctor', 'fitness', 'gym', 'running'],
        'food': ['food', 'dinner', 'lunch', 'breakfast', 'meal', 'cooking', 'restaurant'],
        'travel': ['travel', 'trip', 'vacation', 'journey', 'flight', 'hotel'],
        'learning': ['learning', 'study', 'read', 'book', 'class', 'course'],
        'friends': ['friend', 'social', 'party', 'hangout', 'gathering'],
        'goals': ['goal', 'plan', 'future', 'aspiration', 'dream', 'objective'],
        'reflection': ['reflection', 'thinking', 'contemplation', 'introspection', 'mindfulness']
    }

    # Convert content to lowercase for case-insensitive matching
    content_lower = content.lower()

    # Check for topic keywords in content
    for topic, keywords in topic_keywords.items():
        for keyword in keywords:
            if keyword in content_lower:
                tags.add(topic)
                break

    # Add mood as a tag if provided
    if mood:
        tags.add(mood.lower())

    return list(tags)

@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_user_biography(user, chapter=None):
    """
    Generate a comprehensive biography for the user based on their journal entries
    """
    request_id = int(time.time() * 1000)
    logger.info(f"Biography generation {request_id} started for user {user.username}")

    try:
        # Get all entries for this user
        entries = Entry.objects.filter(user=user).order_by('-created_at')

        if not entries:
            logger.warning(f"No journal entries found for user {user.username}")
            return "Add more journal entries to generate your biography. Your life story will be crafted based on your journaling history."

        # Get entry content samples (limit to prevent token overflow)
        entry_samples = []
        for entry in entries[:20]:  # Use up to 20 most recent entries
            entry_samples.append({
                'date': entry.created_at.strftime('%Y-%m-%d'),
                'title': entry.title,
                'content': entry.content[:300] + "..." if len(entry.content) > 300 else entry.content,
                'mood': entry.mood if hasattr(entry, 'mood') else 'unknown',
                'tags': ", ".join([tag.name for tag in entry.tags.all()]) if hasattr(entry, 'tags') else ''
            })

        # Get user insights if available
        insights = UserInsight.objects.filter(user=user)
        insight_texts = [f"{insight.title}: {insight.content}" for insight in insights]

        # Format entries and insights as context for the API
        entries_text = json.dumps(entry_samples, indent=2)
        insights_text = "\n".join(insight_texts) if insight_texts else "No insights available yet."

        # Determine which chapter to generate
        chapter_content = ""
        if chapter:
            chapter_obj = None
            try:
                chapter_obj = LifeChapter.objects.get(user=user, title__iexact=chapter) or \
                             LifeChapter.objects.get(user=user, slug__iexact=chapter)

                chapter_title = chapter_obj.title
                chapter_description = chapter_obj.description

            except LifeChapter.DoesNotExist:
                # Use the provided chapter name directly
                chapter_title = chapter
                chapter_description = f"Events related to {chapter}"

            chapter_content = f"""
            Focus on generating content for the chapter: "{chapter_title}"
            Chapter description: {chapter_description}

            This should be a cohesive section focusing specifically on this area of the user's life.
            """

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.GROK_API_KEY}',
            'X-Request-ID': str(request_id)
        }

        prompt = f"""
        Generate a thoughtful, biographical narrative based on the user's journal entries.

        USER'S JOURNAL ENTRIES (sample):
        {entries_text}

        USER'S INSIGHTS:
        {insights_text}

        {chapter_content}

        Guidelines:
        1. Write in third person, as if this is a biography about the person's life
        2. Maintain a respectful, reflective tone
        3. Extract themes, patterns, and significant events from their entries
        4. Create a coherent narrative that captures their personality and experiences
        5. Avoid inventing major life events not supported by the entries
        6. Use elegant, thoughtful language appropriate for a biographical work
        7. Organize content into meaningful paragraphs with good flow
        8. Length should be approximately 800-1200 words
        """

        payload = {
            'model': 'llama3-70b-8192',
            'messages': [
                {'role': 'system', 'content': 'You are a skilled biographer who creates compelling life narratives based on journal entries.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 1500
        }

        start_time = time.time()
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=30  # Biography generation needs more time
        )
        api_time = time.time() - start_time

        logger.info(f"Biography generation {request_id} completed in {api_time:.2f}s with status {response.status_code}")

        if response.status_code != 200:
            logger.error(f"Biography generation {request_id} failed: {response.status_code} - {response.text}")
            raise RequestException(f"API returned status code {response.status_code}")

        response_data = response.json()

        # Validate response structure
        if 'choices' not in response_data or not response_data['choices']:
            error_msg = f"Invalid API response structure: {response_data}"
            logger.error(f"Biography generation {request_id}: {error_msg}")
            raise ValueError(error_msg)

        biography_content = response_data['choices'][0]['message']['content']

        # Store the generated biography or chapter
        if chapter:
            # Store as a chapter of the biography
            biography, created = Biography.objects.get_or_create(user=user)

            # Update the specific chapter content in the biography object
            chapter_key = chapter.lower().replace(' ', '_')
            chapters_data = biography.chapters_data or {}
            chapters_data[chapter_key] = {
                'title': chapter,
                'content': biography_content,
                'last_updated': timezone.now().isoformat()
            }
            biography.chapters_data = chapters_data
            biography.save()

            return biography_content
        else:
            # Store as the main biography content
            biography, created = Biography.objects.get_or_create(user=user)
            biography.content = biography_content
            biography.last_updated = timezone.now()
            biography.save()

            return biography_content

    except Exception as e:
        logger.error(f"Biography generation {request_id} error: {str(e)}", exc_info=True)
        raise

@login_required
def generate_biography_api(request):
    """API endpoint to generate a biography or specific chapter"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        # Check if a specific chapter was requested
        chapter = request.GET.get('chapter')

        # Generate the biography or chapter
        content = AIService.generate_user_biography(request.user, chapter=chapter)

        return JsonResponse({
            'success': True,
            'content': content,
            'generated_at': timezone.now().isoformat()
        })
    except Exception as e:
        logger.error(f"API biography generation error: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def save_generated_entry(request):
    """Save a generated journal entry to the database"""
    try:
        data = json.loads(request.body)
        title = data.get('title')
        content = data.get('content')

        # Store in session regardless of authentication status
        request.session['pending_entry'] = {
            'title': title,
            'content': content,
            'mood': data.get('mood'),
            'tags': data.get('tags', [])
        }

        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'login_required': True,
                'message': 'Please log in to save your entry'
            }, status=401)

        # User is authenticated, proceed with saving
        if not title or not content:
            return JsonResponse({'success': False, 'error': 'Missing title or content'}, status=400)

        # Create the new entry
        entry = Entry.objects.create(
            user=request.user,
            title=title,
            content=content,
            mood=data.get('mood')
        )

        # Add tags if provided
        tags = data.get('tags', [])
        if not tags and content:
            # Auto-generate tags if none were provided
            tags = auto_generate_tags(content, data.get('mood'))

        if tags:
            for tag_name in tags:
                tag, created = Tag.objects.get_or_create(
                    name=tag_name.lower().strip(),
                    user=request.user
                )
                entry.tags.add(tag)

        # Clear the pending entry from session
        if 'pending_entry' in request.session:
            del request.session['pending_entry']

        return JsonResponse({
            'success': True,
            'entry_id': entry.id,
            'message': 'Entry saved successfully'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error saving generated entry: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Server error while saving entry',
            'details': str(e)
        }, status=500)

@receiver(user_logged_in)
def save_pending_entry(sender, user, request, **kwargs):
    """Save any pending entry after user logs in"""
    if 'pending_entry' in request.session:
        entry_data = request.session.pop('pending_entry')

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
            AIService.generate_entry_summary(entry)
        except Exception as e:
            logger.error(f"Failed to generate summary for pending entry: {str(e)}")

        # Set a flag to indicate entry was saved
        request.session['entry_saved'] = True
        request.session['saved_entry_id'] = entry.id


class CustomLoginView(LoginView):
    def form_valid(self, form):
        """Process the valid form and check for pending entries"""
        # First do the standard login process
        response = super().form_valid(form)

        # Check for pending entry in session
        pending_entry = self.request.session.get('pending_entry')
        if pending_entry:
            try:
                # Create entry
                entry = Entry.objects.create(
                    user=self.request.user,
                    title=pending_entry.get('title', 'Untitled Entry'),
                    content=pending_entry.get('content', ''),
                    mood=pending_entry.get('mood')
                )

                # Add tags
                tags = pending_entry.get('tags', [])
                if not tags and pending_entry.get('content'):
                    tags = auto_generate_tags(pending_entry.get('content'), pending_entry.get('mood'))

                if tags:
                    for tag_name in tags:
                        tag, created = Tag.objects.get_or_create(
                            name=tag_name.lower().strip(),
                            user=self.request.user
                        )
                        entry.tags.add(tag)

                # Clear pending entry
                del self.request.session['pending_entry']

                # Indicate success
                self.request.session['entry_saved'] = True
                self.request.session['saved_entry_id'] = entry.id

                logger.info(f"Successfully created entry after login with ID: {entry.id}")
            except Exception as e:
                logger.error(f"Error processing pending entry after login: {str(e)}", exc_info=True)

        return response

def custom_login(request):
    """Custom login view that handles save_after_login flag"""
    # Store a flag in session if this is a post-save login
    if 'save_after_login' in request.GET:
        request.session['save_after_login'] = True

    # Use Django's built-in login view
    return auth_views.LoginView.as_view(template_name='diary/login.html')(request)


def gallery_view(request):
    """Main gallery view showing featured journals"""
    # Later, you can fetch actual journal data from your database
    # For now, using mock data

    # Sample featured journals (just for display)
    featured_journals = [
        {
            'id': 1,
            'title': 'Around the World in 80 Days',
            'author': 'adventurer',
            'description': 'A travel journal chronicling adventures across six continents and fifteen countries.',
            'tags': ['Travel', 'Adventure', 'Photography'],
            'likes': 872,
            'views': 4200,
            'tips': 4520,
            'cover_image': 'https://images.unsplash.com/photo-1541410965313-d53b3c16ef17',
            'rank': 1
        },
        {
            'id': 2,
            'title': 'Mindfulness Journey',
            'author': 'mindful_me',
            'description': 'A year of daily meditations and mindfulness practices documented with reflections.',
            'tags': ['Mindfulness', 'Wellness', 'Self-Care'],
            'likes': 621,
            'views': 3180,
            'tips': 3180,
            'cover_image': 'https://images.unsplash.com/photo-1533090161767-e6ffed986c88',
            'rank': 2
        },
        {
            'id': 3,
            'title': 'From Novice to Engineer',
            'author': 'code_chronicles',
            'description': 'A coding journey documenting the path from complete beginner to professional software engineer.',
            'tags': ['Technology', 'Coding', 'Career'],
            'likes': 512,
            'views': 2845,
            'tips': 2845,
            'cover_image': 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97',
            'rank': 3
        },
    ]

    context = {
        'featured_journals': featured_journals,
        'filter_type': 'popular'  # Default filter
    }

    return render(request, 'diary/gallery.html', context)

@login_required
def gallery_publish(request):
    """View for publishing a journal to the gallery"""
    # Placeholder for now
    if request.method == 'POST':
        # Handle publishing logic later
        messages.success(request, "Your journal has been published to the gallery!")
        return redirect('gallery')

    return render(request, 'gallery_publish.html')

def gallery_monetization(request):
    """Information page about monetization"""
    return render(request, 'gallery_monetization.html')

def gallery_contest(request):
    """Weekly contest page"""
    # Sample contest data
    contest_data = {
        'prize': '$100 + Featured Spotlight',
        'ends_in_days': 3,
        'entries_count': 157
    }

    return render(request, 'gallery_contest.html', {'contest': contest_data})

def gallery_faq(request):
    """FAQ about the gallery feature"""
    return render(request, 'gallery_faq.html')

def gallery_journal_detail(request, journal_id):
    """View for a single published journal"""
    # This is a placeholder - later you'll fetch the actual journal by ID
    journal = {
        'id': journal_id,
        'title': 'Sample Journal',
        'description': 'This is a placeholder journal entry.',
        'author': 'username',
        'entries': []  # Would contain actual entries
    }

    return render(request, 'gallery_journal_detail.html', {'journal': journal})

def gallery_author_profile(request, username):
    """View for an author's profile"""
    # This is a placeholder - later you'll fetch the actual user
    try:
        user = User.objects.get(username=username)
        # For now, just basic user info - later you'll add journals
        context = {
            'profile_user': user,
            'journals': []  # Would contain user's journals
        }
        return render(request, 'gallery_author_profile.html', context)
    except User.DoesNotExist:
        messages.error(request, "Author not found")
        return redirect('gallery')
