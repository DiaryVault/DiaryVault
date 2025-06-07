import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from ..models import Entry, Tag, SummaryVersion, LifeChapter, EntryPhoto
from ..forms import EntryForm
from ..services.ai_service import AIService
from ..utils.analytics import get_mood_emoji, get_tag_color

logger = logging.getLogger(__name__)

@login_required
def journal(request):
    """Create a new diary entry"""
    if request.method == 'POST':
        form = EntryForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            # Create the entry object but don't save to the database yet
            entry = form.save(commit=False)
            # Set the user manually
            entry.user = request.user
            # Now save to database
            entry.save()
            # Save many-to-many relationships if any
            form.save_m2m()

            photo_file = request.FILES.get('entry_photo')
            if photo_file:
                EntryPhoto.objects.create(entry=entry, photo=photo_file)

            # Generate AI summary
            AIService.generate_entry_summary(entry)

            messages.success(request, 'Entry saved successfully!')

            # If there are enough entries, regenerate insights
            entry_count = Entry.objects.filter(user=request.user).count()
            if entry_count % 5 == 0:  # Every 5 entries, update insights
                AIService.generate_insights(request.user)

            return redirect('entry_detail', entry_id=entry.id)
    else:
        form = EntryForm(user=request.user)

    return render(request, 'diary/journal.html', {'form': form, 'today': timezone.now()})

@login_required
def entry_detail(request, entry_id):
    """View a single diary entry"""
    entry = get_object_or_404(Entry, pk=entry_id, user=request.user)

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

    # Add debug information about photos
    photos = entry.photos.all()
    photo_count = photos.count()
    photo_info = []

    for photo in photos:
        try:
            photo_info.append({
                'id': photo.id,
                'url': photo.photo.url,
                'exists': photo.photo.storage.exists(photo.photo.name)
            })
        except Exception as e:
            photo_info.append({
                'id': photo.id,
                'error': str(e)
            })

    context = {
        'entry': entry,
        'summary_versions': entry.versions.all(),
        'related_entries': related_entries,
        'debug_photo_count': photo_count,
        'debug_photo_info': photo_info
    }

    return render(request, 'diary/entry_detail.html', context)

@login_required
def edit_entry(request, entry_id):
    """Edit an existing entry using the same template as new entries"""
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)

    if request.method == 'POST':
        form = EntryForm(request.POST, request.FILES, instance=entry, user=request.user)
        if form.is_valid():
            # Create the entry object but don't save to the database yet
            updated_entry = form.save(commit=False)
            # Make sure user is still set correctly (though it should be since we're using instance)
            updated_entry.user = request.user
            # Now save to database
            updated_entry.save()
            # Save many-to-many relationships
            form.save_m2m()

            messages.success(request, "Entry updated successfully!")
            return redirect('entry_detail', entry_id=entry.id)
    else:
        form = EntryForm(instance=entry, user=request.user)

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
    """Optimized library view with tabs for different ways to browse entries"""

    # OPTIMIZED: Use select_related and prefetch_related for better query performance
    all_entries = Entry.objects.filter(user=request.user).select_related(
        'chapter'  # Fetch chapter data in a single query
    ).prefetch_related(
        'tags',    # Prefetch tags to avoid N+1 queries
        'photos'   # Prefetch photos if needed
    ).order_by('-created_at')

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
        # OPTIMIZED: Use the already prefetched queryset
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
        # OPTIMIZED: Use select_related data that's already fetched
        try:
            chapter = LifeChapter.objects.get(id=chapter_filter, user=request.user)
            entries = all_entries.filter(chapter=chapter)
            active_tab = 'time-periods'  # Show in the time periods tab with the chapter books
            active_filter = chapter.title
        except LifeChapter.DoesNotExist:
            # Handle invalid chapter filter gracefully
            chapter_filter = None

    # OPTIMIZED: Get time periods with minimal database queries
    time_periods = {}
    # Group entries by quarter/year using the already fetched data
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

    # OPTIMIZED: Get tags with counts using a single query with annotation
    from django.db.models import Count

    # Get tags with their usage counts in one query
    user_tags = Tag.objects.filter(user=request.user).annotate(
        entry_count=Count('entries', filter=models.Q(entries__user=request.user))
    ).filter(entry_count__gt=0).order_by('-entry_count')

    tags = []
    for tag in user_tags:
        tags.append({
            'id': tag.id,
            'name': tag.name,
            'count': tag.entry_count,
            'active': tag.name == tag_filter  # Mark as active if it's the current filter
        })

    # OPTIMIZED: Get moods with counts using Python aggregation on already fetched data
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

    # OPTIMIZED: Get chapters with counts using annotation
    user_chapters = LifeChapter.objects.filter(user=request.user).annotate(
        entry_count=Count('entries')
    ).order_by('-entry_count')

    chapters = []
    for chapter in user_chapters:
        chapters.append({
            'id': chapter.id,
            'title': chapter.title,
            'description': chapter.description,
            'count': chapter.entry_count,
            'color': chapter.color,
            'active': str(chapter.id) == chapter_filter  # Mark as active if it's the current filter
        })

    # If no specific entries are filtered, use all entries for the respective tabs
    if not tag_filter:
        tagged_entries = all_entries
    if not mood_filter:
        mood_entries = all_entries

    # OPTIMIZED: Calculate counts without additional queries
    total_entries = len(all_entries)  # Use len() since we already have the queryset
    filtered_count = len(entries) if entries != all_entries else total_entries

    context = {
        'time_periods': sorted_periods,
        'tags': tags,
        'moods': moods,
        'chapters': chapters,
        'entries': entries,  # These are the entries filtered by the active parameter
        'tagged_entries': tagged_entries if 'tagged_entries' in locals() else all_entries,
        'mood_entries': mood_entries if 'mood_entries' in locals() else all_entries,
        'total_entries': total_entries,
        'filtered_count': filtered_count,
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
