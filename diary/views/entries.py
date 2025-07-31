import uuid
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.db import models
from django.db.models import Q

from ..models import Entry, Tag, SummaryVersion, EntryPhoto
from ..forms import EntryForm
from ..services.ai_service import AIService
from ..utils.analytics import get_mood_emoji, get_tag_color, auto_generate_tags


logger = logging.getLogger(__name__)

def journal(request):
    """Create a new diary entry - supports both authenticated and anonymous users"""
    # Initialize pending_entry_data at the beginning
    pending_entry_data = None
    
    if request.method == 'POST':
        # Create form without user for validation
        form = EntryForm(request.POST, request.FILES, user=request.user if request.user.is_authenticated else None)
        
        if form.is_valid():
            # Check if user is authenticated
            if request.user.is_authenticated:
                # Normal save for authenticated users
                try:
                    entry = form.save(commit=True, user=request.user)
                    
                    # Calculate rewards if wallet connected
                    wallet_address = request.POST.get('wallet_address') or getattr(request.user, 'wallet_address', None)
                    if wallet_address:
                        word_count = len(entry.content.split())
                        base_reward = word_count // 10
                        wallet_bonus = 5
                        total_rewards = base_reward + wallet_bonus
                        messages.success(request, f'Entry saved! You earned {total_rewards} tokens!')
                    else:
                        messages.success(request, 'Entry saved successfully!')
                    
                    # Clear any pending anonymous entries
                    if 'anonymous_entries' in request.session:
                        del request.session['anonymous_entries']
                    if 'pending_entry' in request.session:
                        del request.session['pending_entry']
                    
                    return redirect('entry_detail', entry_id=entry.id)
                    
                except Exception as e:
                    logger.error(f"Error saving entry: {e}")
                    messages.error(request, "Error saving entry. Please try again.")
            
            else:
                # Anonymous user - save to session
                try:
                    # Get form data as dictionary
                    entry_data = form.save_anonymous()
                    
                    # Generate unique ID for this entry
                    temp_id = str(uuid.uuid4())
                    
                    # Add metadata
                    entry_data['id'] = temp_id
                    entry_data['created_at'] = timezone.now().isoformat()
                    entry_data['is_anonymous'] = True
                    
                    # Check for wallet in session
                    wallet_address = request.POST.get('wallet_address') or request.session.get('wallet_address')
                    if wallet_address:
                        entry_data['wallet_address'] = wallet_address
                    
                    # Store in session
                    if 'anonymous_entries' not in request.session:
                        request.session['anonymous_entries'] = {}
                    
                    request.session['anonymous_entries'][temp_id] = entry_data
                    request.session['pending_entry'] = entry_data
                    request.session.modified = True
                    
                    # Calculate potential rewards
                    word_count = len(entry_data['content'].split())
                    base_reward = word_count // 10
                    wallet_bonus = 5 if wallet_address else 0
                    potential_rewards = base_reward + wallet_bonus
                    
                    # Provide appropriate message based on wallet status
                    if wallet_address:
                        messages.success(
                            request, 
                            f'Entry saved temporarily! Complete your profile to earn {potential_rewards} tokens.'
                        )
                        # Redirect to profile completion
                        return redirect(f"{reverse('web3_complete_profile')}?entry_id={temp_id}")
                    else:
                        messages.success(
                            request, 
                            f'Entry saved temporarily! Connect your wallet to save permanently and earn {potential_rewards} tokens.'
                        )
                        messages.info(
                            request,
                            'Your entry is saved in this browser session. Connect a wallet or create an account to save it permanently.'
                        )
                    
                    # Show the entry preview with wallet prompt
                    return redirect(f"{reverse('journal')}?show_wallet_prompt=true&entry_id={temp_id}")
                    
                except Exception as e:
                    logger.error(f"Error saving anonymous entry: {e}")
                    messages.error(request, "Error saving entry. Please try again.")
        
        else:
            # Form is invalid - show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
    else:
        # GET request - show form
        form = EntryForm(user=request.user if request.user.is_authenticated else None)
        
        # Check for pending entry from session
        entry_id = request.GET.get('entry_id')
        if entry_id and 'anonymous_entries' in request.session:
            anonymous_entries = request.session.get('anonymous_entries', {})
            if entry_id in anonymous_entries:
                pending_entry_data = anonymous_entries[entry_id]
                
                # Pre-populate the form with anonymous data
                initial_data = {
                    'title': pending_entry_data.get('title', ''),
                    'content': pending_entry_data.get('content', ''),
                    'mood': pending_entry_data.get('mood', 'neutral'),
                }
                
                # Handle tags - convert list back to comma-separated string
                tags = pending_entry_data.get('tags', [])
                if isinstance(tags, list):
                    initial_data['tags'] = ', '.join(tags)
                else:
                    initial_data['tags'] = tags
                
                form = EntryForm(
                    initial=initial_data,
                    user=request.user if request.user.is_authenticated else None
                )
                
                # Show message about the pending entry
                if pending_entry_data.get('has_photo'):
                    messages.info(request, 'Note: Photo uploads require an account. The photo was not saved.')
        
        # Check for pending entry after login
        elif 'pending_entry' in request.session and request.user.is_authenticated:
            pending_entry = request.session.get('pending_entry')
            if pending_entry:
                initial_data = {
                    'title': pending_entry.get('title', ''),
                    'content': pending_entry.get('content', ''),
                    'mood': pending_entry.get('mood', 'neutral'),
                }
                
                # Handle tags
                tags = pending_entry.get('tags', [])
                if isinstance(tags, list):
                    initial_data['tags'] = ', '.join(tags)
                else:
                    initial_data['tags'] = tags
                
                form = EntryForm(initial=initial_data, user=request.user)
                messages.info(
                    request, 
                    'Welcome back! Your draft entry has been loaded. Click save to store it permanently.'
                )

    # Get anonymous entries count for display
    anonymous_entries_count = 0
    anonymous_entries_list = []
    if 'anonymous_entries' in request.session:
        anonymous_entries = request.session.get('anonymous_entries', {})
        anonymous_entries_count = len(anonymous_entries)
        # Convert to list for template display
        anonymous_entries_list = [
            {
                'id': entry_id,
                'title': entry_data.get('title', 'Untitled'),
                'created_at': entry_data.get('created_at'),
                'preview': entry_data.get('content', '')[:100] + '...' if len(entry_data.get('content', '')) > 100 else entry_data.get('content', '')
            }
            for entry_id, entry_data in anonymous_entries.items()
        ]

    context = {
        'form': form,
        'today': timezone.now(),
        'is_edit_mode': False,
        'pending_entry': pending_entry_data,
        'is_authenticated': request.user.is_authenticated,
        'show_wallet_prompt': request.GET.get('show_wallet_prompt', False),
        'anonymous_entries_count': anonymous_entries_count,
        'anonymous_entries': anonymous_entries_list,
        'wallet_address': request.session.get('wallet_address'),
        'has_metamask': True,  # You can detect this with JavaScript and pass via form
    }

    return render(request, 'diary/journal.html', context)

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
    all_entries = Entry.objects.filter(user=request.user).prefetch_related(
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
    """Assign an entry to a life chapter - REMOVED since LifeChapter no longer exists"""
    # This function can be removed or redirected since chapters are part of biography
    entry = get_object_or_404(Entry, id=entry_id, user=request.user)
    messages.info(request, "Chapter assignment is no longer available.")
    return redirect('entry_detail', entry_id=entry.id)