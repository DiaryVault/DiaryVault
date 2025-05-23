from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum, Avg, F
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta

from ..models import (
    Journal, JournalTag, JournalLike, JournalPurchase,
    JournalReview, Entry, JournalEntry, Tip
)

def marketplace_view(request):
    """Main marketplace view showing real published journals"""

    # Get filter parameters
    category = request.GET.get('category')
    sort_by = request.GET.get('sort', 'trending')
    search_query = request.GET.get('search', '').strip()
    price_filter = request.GET.get('price')  # 'free', 'premium', 'all'

    # Base queryset - only published journals
    journals = Journal.objects.filter(is_published=True).select_related('author')

    # Apply search filter
    if search_query:
        try:
            journals = journals.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(author__username__icontains=search_query)
            ).distinct()
        except:
            # Fallback if marketplace_tags doesn't exist yet
            journals = journals.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(author__username__icontains=search_query)
            ).distinct()

    # Apply category filter (skip if no categories exist yet)
    if category and category != 'all':
        try:
            journals = journals.filter(marketplace_tags__slug=category)
        except:
            pass  # Skip if marketplace_tags field doesn't exist yet

    # Apply price filter
    if price_filter == 'free':
        try:
            journals = journals.filter(price=0)
        except:
            # Fallback if price field doesn't exist
            journals = journals.all()
    elif price_filter == 'premium':
        try:
            journals = journals.filter(price__gt=0)
        except:
            journals = journals.none()  # No premium journals if no price field

    # Apply sorting
    if sort_by == 'trending':
        try:
            journals = journals.order_by('-popularity_score', '-date_published')
        except:
            # Fallback sorting
            journals = journals.order_by('-view_count', '-created_at')
    elif sort_by == 'mostTipped':
        journals = journals.order_by('-total_tips', '-date_published')
    elif sort_by == 'newest':
        try:
            journals = journals.order_by('-date_published')
        except:
            journals = journals.order_by('-created_at')
    elif sort_by == 'mostLiked':
        try:
            journals = journals.annotate(
                like_count=Count('journal_likes')
            ).order_by('-like_count', '-date_published')
        except:
            journals = journals.annotate(
                like_count=Count('likes')
            ).order_by('-like_count', '-created_at')
    elif sort_by == 'staffPicks':
        journals = journals.filter(is_staff_pick=True).order_by('-date_published')
    else:
        try:
            journals = journals.order_by('-date_published')
        except:
            journals = journals.order_by('-created_at')

    # Get featured journal
    featured_journal = None
    try:
        featured_journal = journals.filter(featured=True).first()
        if not featured_journal:
            featured_journal = journals.order_by('-total_tips').first()
    except:
        # Fallback
        featured_journal = journals.first()

    # Get top earning journals
    top_earning = journals.order_by('-total_tips')[:3]

    # Get popular free journals
    try:
        popular_free = journals.filter(price=0).annotate(
            like_count=Count('likes')
        ).order_by('-like_count', '-view_count')[:5]
    except:
        # Fallback if price field doesn't exist
        popular_free = journals.annotate(
            like_count=Count('likes')
        ).order_by('-like_count', '-view_count')[:5]

    # Get categories with journal counts (optional - skip if model doesn't exist)
    categories = []
    try:
        categories = JournalTag.objects.annotate(
            journal_count=Count('journal', filter=Q(journal__is_published=True))
        ).filter(journal_count__gt=0).order_by('-journal_count')
    except:
        pass  # Skip if JournalTag model doesn't exist yet

    # Pagination
    paginator = Paginator(journals, 12)
    page_number = request.GET.get('page')
    journals_page = paginator.get_page(page_number)

    # Get marketplace statistics
    stats = {
        'total_journals': Journal.objects.filter(is_published=True).count(),
        'total_authors': User.objects.filter(journals__is_published=True).distinct().count(),
        'total_earnings': Journal.objects.filter(is_published=True).aggregate(
            total=Sum('total_tips')
        )['total'] or 0,
        'total_entries': JournalEntry.objects.filter(journal__is_published=True).count(),
    }

    context = {
        'journals': journals_page,
        'featured_journal': featured_journal,
        'top_earning': top_earning,
        'popular_free': popular_free,
        'categories': categories,
        'stats': stats,
        'current_category': category,
        'current_sort': sort_by,
        'search_query': search_query,
        'price_filter': price_filter,
        'total_results': paginator.count,
    }

    return render(request, 'diary/marketplace.html', context)

@login_required
def publish_journal(request):
    """Create or modify a journal for marketplace publishing"""

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        price = request.POST.get('price', 0)
        selected_entries = request.POST.getlist('entries')
        tag_names = request.POST.get('tags', '').split(',')

        # Validate
        if not title or not description:
            messages.error(request, "Title and description are required.")
            return redirect('publish_journal')

        if not selected_entries:
            messages.error(request, "Please select at least one entry to publish.")
            return redirect('publish_journal')

        try:
            # Create the journal using your existing model
            journal_data = {
                'title': title.strip(),
                'description': description.strip(),
                'author': request.user,
                'is_published': True,
                'privacy_setting': 'public'
            }

            # Add optional fields if they exist
            try:
                journal_data['price'] = float(price) if price else 0.00
                journal_data['date_published'] = timezone.now()
            except:
                pass

            journal = Journal.objects.create(**journal_data)

            # Add selected entries as JournalEntry objects
            for i, entry_id in enumerate(selected_entries):
                try:
                    original_entry = Entry.objects.get(id=entry_id, user=request.user)

                    # Create JournalEntry using your existing model
                    JournalEntry.objects.create(
                        journal=journal,
                        title=original_entry.title,
                        content=original_entry.content,
                        entry_date=original_entry.created_at.date(),
                        is_included=True
                    )

                    # Mark original entry as published (if field exists)
                    try:
                        original_entry.published_in_journal = journal
                        original_entry.save()
                    except:
                        pass  # Skip if field doesn't exist

                except Entry.DoesNotExist:
                    continue

            # Add tags (if JournalTag model exists)
            try:
                for tag_name in tag_names:
                    tag_name = tag_name.strip().lower()
                    if tag_name:
                        tag, created = JournalTag.objects.get_or_create(
                            name=tag_name,
                            defaults={'slug': tag_name.replace(' ', '-')}
                        )
                        journal.marketplace_tags.add(tag)
            except:
                pass  # Skip if tags not implemented yet

            # Update cached statistics (if method exists)
            try:
                journal.update_cached_counts()
            except:
                pass

            messages.success(request, f'Journal "{title}" published successfully!')
            return redirect('marketplace_journal_detail', journal_id=journal.id)

        except Exception as e:
            messages.error(request, f'Error publishing journal: {str(e)}')
            return redirect('publish_journal')

    # GET request - show publish form
    try:
        publishable_entries = Entry.objects.filter(
            user=request.user,
            published_in_journal__isnull=True
        ).exclude(content='').order_by('-created_at')
    except:
        # Fallback if published_in_journal field doesn't exist
        publishable_entries = Entry.objects.filter(
            user=request.user
        ).exclude(content='').order_by('-created_at')

    # Filter entries that meet minimum criteria
    quality_entries = [
        entry for entry in publishable_entries
        if len(entry.content.strip()) >= 100 and entry.title.strip()
    ]

    context = {
        'entries': quality_entries,
        'total_entries': len(quality_entries),
    }

    return render(request, 'diary/publish_journal.html', context)

def marketplace_journal_detail(request, journal_id):
    """View for a single published journal"""
    journal = get_object_or_404(
        Journal.objects.select_related('author'),
        id=journal_id,
        is_published=True
    )

    # Increment view count
    journal.view_count += 1
    journal.save(update_fields=['view_count'])

    # Check if user has access to premium content
    has_access = True
    try:
        if journal.price > 0 and request.user.is_authenticated:
            # Check if user purchased or is the author
            has_access = (
                journal.author == request.user or
                JournalPurchase.objects.filter(
                    user=request.user,
                    journal=journal
                ).exists()
            )
        elif hasattr(journal, 'price') and journal.price > 0:
            has_access = False
    except:
        pass  # Skip premium access check if price field doesn't exist

    # Get entries to display
    entries = journal.entries.filter(is_included=True)

    # Get related journals
    try:
        related_journals = Journal.objects.filter(
            is_published=True
        ).filter(
            Q(author=journal.author) | Q(marketplace_tags__in=journal.marketplace_tags.all())
        ).exclude(id=journal.id).distinct()[:3]
    except:
        # Fallback without tags
        related_journals = Journal.objects.filter(
            is_published=True,
            author=journal.author
        ).exclude(id=journal.id)[:3]

    # Get reviews and ratings (if model exists)
    reviews = []
    avg_rating = None
    try:
        reviews = journal.reviews.select_related('user').order_by('-created_at')[:5]
        avg_rating = journal.reviews.aggregate(avg=Avg('rating'))['avg']
        if avg_rating:
            avg_rating = round(avg_rating, 1)
    except:
        pass

    # Check if current user liked this journal
    user_liked = False
    if request.user.is_authenticated:
        try:
            user_liked = JournalLike.objects.filter(
                user=request.user,
                journal=journal
            ).exists()
        except:
            # Fallback using your existing likes field
            user_liked = journal.likes.filter(id=request.user.id).exists()

    # Get like count
    like_count = 0
    try:
        like_count = JournalLike.objects.filter(journal=journal).count()
    except:
        try:
            like_count = journal.likes.count()
        except:
            like_count = 0

    context = {
        'journal': journal,
        'entries': entries,
        'has_access': has_access,
        'related_journals': related_journals,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'user_liked': user_liked,
        'can_purchase': not has_access and hasattr(journal, 'price') and journal.price > 0,
        'entry_count': entries.count(),
        'like_count': like_count,
    }

    return render(request, 'diary/marketplace_journal_detail.html', context)

@login_required
@require_POST
def like_journal(request, journal_id):
    """Toggle like for a journal"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    try:
        # Try using JournalLike model first
        like, created = JournalLike.objects.get_or_create(
            user=request.user,
            journal=journal
        )

        if not created:
            # Unlike
            like.delete()
            liked = False
        else:
            # Like
            liked = True

        # Update cached count if method exists
        try:
            journal.update_cached_counts()
            like_count = journal.like_count_cached
        except:
            like_count = JournalLike.objects.filter(journal=journal).count()

    except:
        # Fallback to your existing likes ManyToMany field
        if request.user in journal.likes.all():
            journal.likes.remove(request.user)
            liked = False
        else:
            journal.likes.add(request.user)
            liked = True

        like_count = journal.likes.count()

    return JsonResponse({
        'success': True,
        'liked': liked,
        'like_count': like_count
    })

@login_required
@require_POST
def tip_author(request, journal_id):
    """Send a tip to journal author"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    if journal.author == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot tip yourself'})

    try:
        amount = float(request.POST.get('amount', 0))
        message = request.POST.get('message', '').strip()

        if amount <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid tip amount'})

        # Create tip record using your existing Tip model
        tip = Tip.objects.create(
            journal=journal,
            tipper=request.user,
            recipient=journal.author,
            amount=amount
        )

        return JsonResponse({
            'success': True,
            'message': f'Tip of ${amount:.2f} sent successfully!'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def marketplace_author_profile(request, username):
    """View for an author's profile"""
    author = get_object_or_404(User, username=username)

    # Get author's published journals
    journals = Journal.objects.filter(
        author=author,
        is_published=True
    ).order_by('-date_published')

    # Author statistics
    total_earnings = journals.aggregate(total=Sum('total_tips'))['total'] or 0

    # Get total likes
    total_likes = 0
    try:
        total_likes = sum(j.like_count_cached for j in journals if hasattr(j, 'like_count_cached'))
    except:
        # Fallback
        total_likes = sum(j.likes.count() for j in journals)

    total_views = sum(j.view_count for j in journals)

    # Recent tips received
    recent_tips = []
    try:
        recent_tips = Tip.objects.filter(
            recipient=author
        ).select_related('tipper', 'journal').order_by('-created_at')[:5]
    except:
        pass

    context = {
        'author': author,
        'journals': journals,
        'journal_count': journals.count(),
        'total_earnings': total_earnings,
        'total_likes': total_likes,
        'total_views': total_views,
        'recent_tips': recent_tips,
    }

    return render(request, 'diary/marketplace_author_profile.html', context)

# Keep your existing placeholder views for additional pages
def marketplace_monetization(request):
    """Information page about monetization"""
    return render(request, 'diary/marketplace_monetization.html')

def marketplace_contest(request):
    """Weekly contest page"""
    contest_data = {
        'prize': '$100 + Featured Spotlight',
        'ends_in_days': 3,
        'entries_count': 157
    }
    return render(request, 'diary/marketplace_contest.html', {'contest': contest_data})

def marketplace_faq(request):
    """FAQ about the marketplace feature"""
    return render(request, 'diary/marketplace_faq.html')
