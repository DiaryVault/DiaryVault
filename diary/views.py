from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.views.decorators.http import require_POST
from requests.exceptions import Timeout, ConnectionError, RequestException
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from functools import wraps
from datetime import datetime
import time

from datetime import timedelta

from .models import Entry, Tag, SummaryVersion, LifeChapter, Biography, UserInsight, UserPreference
from .forms import EntryForm, SignUpForm, LifeChapterForm
from .ai_services import AIService

import json
import requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
import logging

from django.core.cache import cache
import hashlib

def get_content_hash(journal_content):
    """Create a unique hash for the journal content to use as cache key"""
    return hashlib.md5(journal_content.encode('utf-8')).hexdigest()

logger = logging.getLogger(__name__)

def home(request):
    """Landing page for non-logged in users"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    return render(request, 'diary/landing.html')

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
            entry = form.save(commit=True, user=request.user)

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

    if request.method == 'POST':
        if 'generate_biography' in request.POST:
            # Generate new biography
            biography = AIService.generate_biography(request.user)
            messages.success(request, 'Biography generated successfully!')
            return redirect('biography')

    entries_by_chapter = {}
    chapters = LifeChapter.objects.filter(user=request.user)

    for chapter in chapters:
        entries_by_chapter[chapter] = Entry.objects.filter(
            user=request.user
            # chapters=chapter
        ).order_by('-created_at')[:5]

    context = {
        'biography': biography,
        'entries_by_chapter': entries_by_chapter,
        'total_entries': Entry.objects.filter(user=request.user).count()
    }

    return render(request, 'diary/biography.html', context)

@login_required
def insights(request):
    """View AI-generated insights"""
    insights = UserInsight.objects.filter(user=request.user)

    if request.method == 'POST':
        if 'regenerate_insights' in request.POST:
            # Regenerate insights
            AIService.generate_insights(request.user)
            messages.success(request, 'Insights regenerated!')
            return redirect('insights')

    patterns = insights.filter(insight_type='pattern')
    suggestions = insights.filter(insight_type='suggestion')
    mood = insights.filter(insight_type='mood').first()

    # Group entries by tag for topic distribution
    tags = Tag.objects.filter(user=request.user)
    tag_counts = []

    for tag in tags:
        count = Entry.objects.filter(user=request.user, tags=tag).count()
        if count > 0:
            tag_counts.append({
                'name': tag.name,
                'count': count
            })

    # Sort by count
    tag_counts.sort(key=lambda x: x['count'], reverse=True)

    # Calculate percentages for top tags
    total_tagged = sum(item['count'] for item in tag_counts)
    if total_tagged > 0:
        for item in tag_counts:
            item['percentage'] = int((item['count'] / total_tagged) * 100)

    context = {
        'patterns': patterns,
        'suggestions': suggestions,
        'mood_analysis': mood,
        'tag_distribution': tag_counts[:5]  # Top 5 tags
    }

    return render(request, 'diary/insights.html', context)

# Placeholder for the remaining views that would be needed
# These are just simple implementations to make the URLs work
@login_required
def edit_entry(request, entry_id):
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)
    return render(request, 'diary/edit_entry.html', {'entry': entry})

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

@login_required
def library(request):
    """Library view with tabs for different ways to browse entries"""
    # Get user entries
    entries = Entry.objects.filter(user=request.user).order_by('-created_at')

    # Get time periods (same code as in dashboard)
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

    # Get tags with counts
    tags = []
    for tag in Tag.objects.filter(user=request.user):
        count = entries.filter(tags=tag).count()
        if count > 0:
            tags.append({
                'name': tag.name,
                'count': count
            })

    # Sort tags by count
    tags.sort(key=lambda x: x['count'], reverse=True)

    # Get moods with counts (this depends on your model structure)
    moods = []
    # Example: If you store moods as strings in Entry model
    mood_counts = {}
    for entry in entries:
        if entry.mood:
            if entry.mood not in mood_counts:
                mood_counts[entry.mood] = {
                    'name': entry.mood,
                    'count': 0,
                    'emoji': '😊'  # Default emoji, you might want to map these
                }
            mood_counts[entry.mood]['count'] += 1

    moods = list(mood_counts.values())
    moods.sort(key=lambda x: x['count'], reverse=True)

    context = {
        'time_periods': sorted_periods,
        'tags': tags,
        'moods': moods,
        'entries': entries,
        'total_entries': entries.count(),
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

        prompt = f"""
        Transform the following daily activities into a reflective, well-written journal entry.
        Add emotional depth, insights, and reflection while staying true to the events mentioned.

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
