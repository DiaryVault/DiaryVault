from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta

from .models import Entry, Tag, SummaryVersion, LifeChapter, Biography, UserInsight
from .forms import EntryForm, SignUpForm, LifeChapterForm
from .ai_services import AIService

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
