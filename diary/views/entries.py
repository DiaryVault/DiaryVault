import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from ..models import Entry, Tag, SummaryVersion, LifeChapter
from ..forms import EntryForm
from ..services.ai_service import AIService
from ..utils.analytics import get_mood_emoji, get_tag_color

logger = logging.getLogger(__name__)

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
def assign_to_chapter(request, entry_id):
    """Assign an entry to a life chapter"""
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)
    chapters = LifeChapter.objects.filter(user=request.user)
    return render(request, 'diary/assign_to_chapter.html', {'entry': entry, 'chapters': chapters})
