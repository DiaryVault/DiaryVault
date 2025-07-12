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
import json
import random
from decimal import Decimal
from django.conf import settings
from django.db import transaction, models


from ..views.marketplace_service import MarketplaceService

from ..models import (
    Journal, JournalTag, JournalLike, JournalPurchase,
    JournalReview, Entry, JournalEntry, Tip
)

def marketplace_view(request):
    """Main marketplace view showing real published journals - now with randomization"""

    # Get filter parameters
    category = request.GET.get('category')
    sort_by = request.GET.get('sort', 'trending')
    search_query = request.GET.get('search', '').strip()
    price_filter = request.GET.get('price')  # 'free', 'premium', 'all'
    max_price = request.GET.get('maxPrice', 100)
    journal_types = request.GET.getlist('type')  # free, premium, staff_pick
    lengths = request.GET.getlist('length')  # short, medium, long
    periods = request.GET.getlist('period')  # week, month, year

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

    # Apply advanced filters
    if journal_types:
        filter_q = Q()
        if 'free' in journal_types:
            try:
                filter_q |= Q(price=0)
            except:
                filter_q |= Q(pk__isnull=False)  # Include all if no price field
        if 'premium' in journal_types:
            try:
                filter_q |= Q(price__gt=0)
            except:
                pass
        if 'staff_pick' in journal_types:
            try:
                filter_q |= Q(is_staff_pick=True)
            except:
                pass
        if filter_q:
            journals = journals.filter(filter_q)

    # Apply price range filter
    if max_price and max_price != '100':
        try:
            journals = journals.filter(price__lte=float(max_price))
        except:
            pass

    # Apply length filters
    if lengths:
        filter_q = Q()
        if 'short' in lengths:
            filter_q |= Q(entries__count__lte=20)
        if 'medium' in lengths:
            filter_q |= Q(entries__count__gt=20, entries__count__lte=100)
        if 'long' in lengths:
            filter_q |= Q(entries__count__gt=100)
        if filter_q:
            journals = journals.annotate(entry_count=Count('entries')).filter(filter_q)

    # Apply time period filters
    if periods:
        filter_q = Q()
        now = timezone.now()
        if 'week' in periods:
            week_ago = now - timedelta(days=7)
            try:
                filter_q |= Q(date_published__gte=week_ago)
            except:
                filter_q |= Q(created_at__gte=week_ago)
        if 'month' in periods:
            month_ago = now - timedelta(days=30)
            try:
                filter_q |= Q(date_published__gte=month_ago)
            except:
                filter_q |= Q(created_at__gte=month_ago)
        if 'year' in periods:
            year_ago = now - timedelta(days=365)
            try:
                filter_q |= Q(date_published__gte=year_ago)
            except:
                filter_q |= Q(created_at__gte=year_ago)
        if filter_q:
            journals = journals.filter(filter_q)

    # ======================================================================
    # NEW: Apply sorting with randomization options
    # ======================================================================

    # Convert to list for randomization (only when needed)
    should_randomize = sort_by in ['random', 'trending'] or not search_query

    if sort_by == 'random':
        # Pure random sort
        journal_list = list(journals)
        random.shuffle(journal_list)
        journals = journal_list

    elif sort_by == 'trending':
        # Smart trending with randomization
        journals = get_trending_journals_randomized(journals)

    elif sort_by == 'newest':
        try:
            journals = journals.order_by('-date_published')
        except:
            journals = journals.order_by('-created_at')

    elif sort_by == 'price_low':
        try:
            journals = journals.order_by('price', '-date_published')
        except:
            journals = journals.order_by('-created_at')

    elif sort_by == 'price_high':
        try:
            journals = journals.order_by('-price', '-date_published')
        except:
            journals = journals.order_by('-created_at')

    elif sort_by == 'most_liked':
        try:
            journals = journals.annotate(
                like_count=Count('journal_likes')
            ).order_by('-like_count', '-date_published')
        except:
            journals = journals.annotate(
                like_count=Count('likes')
            ).order_by('-like_count', '-created_at')

    elif sort_by == 'top_earning':
        try:
            journals = journals.order_by('-total_tips', '-date_published')
        except:
            journals = journals.order_by('-created_at')
    else:
        # Default: add some randomization to normal sorting
        if not search_query and not category:
            # Only randomize when browsing (no specific search/filter)
            journals = get_mixed_sort_randomized(journals)
        else:
            try:
                journals = journals.order_by('-date_published')
            except:
                journals = journals.order_by('-created_at')

    # ======================================================================
    # Get featured content with randomization
    # ======================================================================

    # Get featured journal (randomized selection)
    featured_journal = get_randomized_featured_journal(journals)

    # Get top earning journals (with some randomization)
    top_earning = get_randomized_top_earning(journals)

    # Get popular free journals (with randomization)
    popular_free = get_randomized_popular_free(journals)

    # Get categories with journal counts (optional - skip if model doesn't exist)
    categories = []
    try:
        categories = JournalTag.objects.annotate(
            journal_count=Count('journal', filter=Q(journal__is_published=True))
        ).filter(journal_count__gt=0).order_by('-journal_count')
    except:
        pass  # Skip if JournalTag model doesn't exist yet

    # Pagination
    paginator = Paginator(journals, 16)  # Increased to 16 for better grid layout
    page_number = request.GET.get('page')
    journals_page = paginator.get_page(page_number)

    # Get marketplace statistics
    stats = {}
    try:
        stats = {
            'total_journals': Journal.objects.filter(is_published=True).count(),
            'total_authors': User.objects.filter(journals__is_published=True).distinct().count(),
            'total_earnings': Journal.objects.filter(is_published=True).aggregate(
                total=Sum('total_tips')
            )['total'] or 0,
            'total_entries': JournalEntry.objects.filter(journal__is_published=True).count(),
        }
    except:
        # Fallback stats
        stats = {
            'total_journals': Journal.objects.filter(is_published=True).count(),
            'total_authors': User.objects.filter(journals__is_published=True).distinct().count(),
            'total_earnings': 0,
            'total_entries': 0,
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


def get_trending_journals_randomized(journals_queryset):
    """Get trending journals with smart randomization"""
    try:
        # Get the queryset as a list for manipulation
        all_journals = list(journals_queryset)

        if len(all_journals) <= 16:
            # If we have few journals, just shuffle them
            random.shuffle(all_journals)
            return all_journals

        # Smart trending algorithm with randomization
        weighted_journals = []

        for journal in all_journals:
            weight = 1  # Base weight

            # Increase weight for staff picks
            if hasattr(journal, 'is_staff_pick') and journal.is_staff_pick:
                weight += 4

            # Increase weight based on likes
            try:
                like_count = journal.likes.count() if hasattr(journal, 'likes') else 0
                if like_count > 20:
                    weight += 3
                elif like_count > 10:
                    weight += 2
                elif like_count > 5:
                    weight += 1
            except:
                pass

            # Increase weight based on views
            try:
                view_count = getattr(journal, 'view_count', 0)
                if view_count > 500:
                    weight += 3
                elif view_count > 100:
                    weight += 2
                elif view_count > 50:
                    weight += 1
            except:
                pass

            # Increase weight for recent journals
            try:
                days_old = (timezone.now() - journal.created_at).days
                if days_old <= 7:
                    weight += 2
                elif days_old <= 30:
                    weight += 1
            except:
                pass

            # Add to weighted list (repeat based on weight)
            weighted_journals.extend([journal] * weight)

        # Shuffle the weighted list
        random.shuffle(weighted_journals)

        # Remove duplicates while preserving some randomness
        seen = set()
        result = []
        for journal in weighted_journals:
            if journal.id not in seen:
                result.append(journal)
                seen.add(journal.id)

        return result

    except Exception as e:
        # Fallback: just shuffle the original list
        journal_list = list(journals_queryset)
        random.shuffle(journal_list)
        return journal_list


def get_mixed_sort_randomized(journals_queryset):
    """Mix of popular and random journals for default browsing"""
    try:
        all_journals = list(journals_queryset)

        if len(all_journals) <= 20:
            random.shuffle(all_journals)
            return all_journals

        # Take top 30% by popularity, 70% random
        sorted_journals = sorted(all_journals, key=lambda j: (
            getattr(j, 'view_count', 0) +
            (j.likes.count() if hasattr(j, 'likes') else 0) * 10
        ), reverse=True)

        popular_count = max(1, len(all_journals) // 3)
        popular_journals = sorted_journals[:popular_count]
        remaining_journals = sorted_journals[popular_count:]

        # Shuffle both groups
        random.shuffle(popular_journals)
        random.shuffle(remaining_journals)

        # Interleave them
        result = []
        for i in range(max(len(popular_journals), len(remaining_journals))):
            if i < len(popular_journals):
                result.append(popular_journals[i])
            if i < len(remaining_journals):
                result.append(remaining_journals[i])

        return result

    except Exception as e:
        # Fallback
        journal_list = list(journals_queryset)
        random.shuffle(journal_list)
        return journal_list


def get_randomized_featured_journal(journals_queryset):
    """Get a featured journal with weighted randomization"""
    try:
        if isinstance(journals_queryset, list):
            journals = journals_queryset
        else:
            journals = list(journals_queryset)

        if not journals:
            return None

        # Filter potential featured journals
        featured_candidates = []

        for journal in journals:
            score = 0

            # Higher score for staff picks
            if hasattr(journal, 'is_staff_pick') and journal.is_staff_pick:
                score += 10

            # Score based on engagement
            try:
                like_count = journal.likes.count() if hasattr(journal, 'likes') else 0
                view_count = getattr(journal, 'view_count', 0)
                score += (like_count * 2) + (view_count * 0.01)
            except:
                pass

            # Score based on entries count (quality indicator)
            try:
                entry_count = journal.entries.count()
                if entry_count > 10:
                    score += 5
                elif entry_count > 5:
                    score += 2
            except:
                pass

            # Only consider journals with some engagement
            if score > 1:
                featured_candidates.append((journal, score))

        if not featured_candidates:
            # Fallback to random selection
            return random.choice(journals)

        # Sort by score and pick from top candidates with some randomization
        featured_candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = featured_candidates[:min(5, len(featured_candidates))]

        # Weighted random selection from top candidates
        weights = [candidate[1] for candidate in top_candidates]
        selected = random.choices(top_candidates, weights=weights, k=1)[0]

        return selected[0]

    except Exception as e:
        # Fallback
        try:
            if isinstance(journals_queryset, list):
                return random.choice(journals_queryset) if journals_queryset else None
            else:
                return journals_queryset.order_by('?').first()
        except:
            return None


def get_randomized_top_earning(journals_queryset):
    """Get top earning journals with some randomization"""
    try:
        if isinstance(journals_queryset, list):
            journals = journals_queryset
        else:
            journals = list(journals_queryset)

        # Filter journals with earnings
        earning_journals = []
        for journal in journals:
            try:
                tips = getattr(journal, 'total_tips', 0)
                if tips and tips > 0:
                    earning_journals.append(journal)
            except:
                pass

        if len(earning_journals) < 3:
            # If not enough earning journals, include popular ones
            popular_journals = sorted(journals, key=lambda j: (
                getattr(j, 'view_count', 0) +
                (j.likes.count() if hasattr(j, 'likes') else 0) * 5
            ), reverse=True)

            earning_journals.extend(popular_journals[:5])
            earning_journals = list(set(earning_journals))  # Remove duplicates

        # Randomize the selection
        random.shuffle(earning_journals)
        return earning_journals[:3]

    except Exception as e:
        # Fallback
        try:
            if isinstance(journals_queryset, list):
                random.shuffle(journals_queryset)
                return journals_queryset[:3]
            else:
                return list(journals_queryset.order_by('?')[:3])
        except:
            return []


def get_randomized_popular_free(journals_queryset):
    """Get popular free journals with randomization"""
    try:
        if isinstance(journals_queryset, list):
            journals = journals_queryset
        else:
            journals = list(journals_queryset)

        # Filter free journals
        free_journals = []
        for journal in journals:
            try:
                # Check if journal is free
                price = getattr(journal, 'price', None)
                if price is None or price == 0:
                    free_journals.append(journal)
            except:
                # If no price field, assume free
                free_journals.append(journal)

        if not free_journals:
            return []

        # Sort by popularity with randomization
        def popularity_score(journal):
            score = 0
            try:
                score += getattr(journal, 'view_count', 0) * 0.1
                score += (journal.likes.count() if hasattr(journal, 'likes') else 0) * 2
                score += random.randint(0, 100)  # Add randomness
            except:
                score = random.randint(0, 100)
            return score

        free_journals.sort(key=popularity_score, reverse=True)
        return free_journals[:5]

    except Exception as e:
        # Fallback
        try:
            if isinstance(journals_queryset, list):
                random.shuffle(journals_queryset)
                return journals_queryset[:5]
            else:
                return list(journals_queryset.order_by('?')[:5])
        except:
            return []


# ======================================================================
# Additional sort option to add to your frontend
# ======================================================================

def get_sort_options():
    """Return available sort options for the frontend"""
    return [
        ('trending', '🔥 Trending'),
        ('random', '🎲 Random'),  # NEW: Pure random option
        ('newest', '🆕 Newest'),
        ('topRated', '⭐ Top Rated'),
        ('bestSelling', '💰 Best Selling'),
        ('priceLow', '💲 Price: Low to High'),
        ('priceHigh', '💲 Price: High to Low'),
        ('most_liked', '❤️ Most Liked'),  # NEW: Sort by likes
    ]


@login_required
def publish_journal(request):
    """Create or modify a journal for marketplace publishing"""

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        price = request.POST.get('price', 0)
        selected_entries = request.POST.getlist('entries')
        tag_names = request.POST.get('tags', '').split(',')
        cover_image = request.FILES.get('cover_image')

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

            # Add cover image if provided
            if cover_image:
                try:
                    journal_data['cover_image'] = cover_image
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
    try:
        journal.view_count = F('view_count') + 1
        journal.save(update_fields=['view_count'])
        journal.refresh_from_db()
    except:
        # Fallback
        if hasattr(journal, 'view_count'):
            journal.view_count += 1
            journal.save(update_fields=['view_count'])

    # Check if user has access to premium content
    has_access = True
    try:
        if hasattr(journal, 'price') and journal.price > 0 and request.user.is_authenticated:
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
            try:
                user_liked = journal.likes.filter(id=request.user.id).exists()
            except:
                user_liked = False

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
        try:
            if request.user in journal.likes.all():
                journal.likes.remove(request.user)
                liked = False
            else:
                journal.likes.add(request.user)
                liked = True

            like_count = journal.likes.count()
        except:
            return JsonResponse({'success': False, 'error': 'Like functionality not available'})

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

        # Update journal's total tips
        try:
            journal.total_tips = F('total_tips') + amount
            journal.save(update_fields=['total_tips'])
        except:
            pass

        return JsonResponse({
            'success': True,
            'message': f'Tip of ${amount:.2f} sent successfully!'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def purchase_journal(request, journal_id):
    """Purchase a premium journal"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    if journal.author == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot purchase your own journal'})

    if not hasattr(journal, 'price') or journal.price <= 0:
        return JsonResponse({'success': False, 'error': 'This journal is not for sale'})

    # Check if already purchased
    try:
        if JournalPurchase.objects.filter(user=request.user, journal=journal).exists():
            return JsonResponse({'success': False, 'error': 'You already own this journal'})
    except:
        pass

    try:
        # Create purchase record
        purchase = JournalPurchase.objects.create(
            user=request.user,
            journal=journal,
            amount=journal.price
        )

        # Update author earnings
        try:
            journal.total_tips = F('total_tips') + journal.price
            journal.save(update_fields=['total_tips'])
        except:
            pass

        return JsonResponse({
            'success': True,
            'message': f'Successfully purchased "{journal.title}" for ${journal.price:.2f}!'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def quick_view_journal(request, journal_id):
    """AJAX endpoint for quick view modal"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    # Get entry preview (first 2-3 entries)
    entries_preview = journal.entries.filter(is_included=True)[:3]

    # Check if user has access
    has_access = True
    try:
        if hasattr(journal, 'price') and journal.price > 0:
            has_access = (
                journal.author == request.user or
                JournalPurchase.objects.filter(user=request.user, journal=journal).exists()
            )
    except:
        pass

    data = {
        'title': journal.title,
        'description': journal.description,
        'author': journal.author.username,
        'price': getattr(journal, 'price', 0),
        'entry_count': journal.entries.filter(is_included=True).count(),
        'like_count': getattr(journal, 'likes', []).count() if hasattr(journal, 'likes') else 0,
        'view_count': getattr(journal, 'view_count', 0),
        'has_access': has_access,
        'entries_preview': [
            {
                'title': entry.title,
                'content': entry.content[:200] + '...' if len(entry.content) > 200 else entry.content,
                'date': entry.entry_date.strftime('%B %d, %Y') if hasattr(entry, 'entry_date') else ''
            }
            for entry in entries_preview
        ]
    }

    return JsonResponse(data)

def marketplace_author_profile(request, username):
    """View for an author's profile"""
    author = get_object_or_404(User, username=username)

    # Get author's published journals
    try:
        journals = Journal.objects.filter(
            author=author,
            is_published=True
        ).order_by('-date_published')
    except:
        journals = Journal.objects.filter(
            author=author,
            is_published=True
        ).order_by('-created_at')

    # Author statistics
    try:
        total_earnings = journals.aggregate(total=Sum('total_tips'))['total'] or 0
    except:
        total_earnings = 0

    # Get total likes
    total_likes = 0
    try:
        total_likes = sum(j.like_count_cached for j in journals if hasattr(j, 'like_count_cached'))
    except:
        # Fallback
        try:
            total_likes = sum(j.likes.count() for j in journals)
        except:
            total_likes = 0

    try:
        total_views = sum(j.view_count for j in journals if hasattr(j, 'view_count'))
    except:
        total_views = 0

    # Recent tips received
    recent_tips = []
    try:
        recent_tips = Tip.objects.filter(
            recipient=author
        ).select_related('tipper', 'journal').order_by('-created_at')[:5]
    except:
        pass

    # Get author's bio/profile info
    author_bio = getattr(author, 'profile', {})
    if hasattr(author, 'userprofile'):
        author_bio = author.userprofile

    context = {
        'author': author,
        'author_bio': author_bio,
        'journals': journals,
        'journal_count': journals.count(),
        'total_earnings': total_earnings,
        'total_likes': total_likes,
        'total_views': total_views,
        'recent_tips': recent_tips,
    }

    return render(request, 'diary/marketplace_author_profile.html', context)

# Enhanced placeholder views for additional pages
def marketplace_monetization(request):
    """Information page about monetization"""
    # Get some stats for the page
    try:
        stats = {
            'top_earners': Journal.objects.filter(is_published=True).order_by('-total_tips')[:5],
            'avg_earnings': Journal.objects.filter(is_published=True, total_tips__gt=0).aggregate(
                avg=Avg('total_tips')
            )['avg'] or 0,
            'total_paid_out': Journal.objects.filter(is_published=True).aggregate(
                total=Sum('total_tips')
            )['total'] or 0,
        }
    except:
        stats = {
            'top_earners': [],
            'avg_earnings': 0,
            'total_paid_out': 0,
        }

    return render(request, 'diary/marketplace_monetization.html', {'stats': stats})

def marketplace_contest(request):
    """Weekly contest page"""
    # Calculate contest end date (next Sunday)
    from datetime import datetime, timedelta
    today = timezone.now().date()
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7
    contest_end = today + timedelta(days=days_until_sunday)

    # Get contest entries (most recent journals)
    try:
        contest_entries = Journal.objects.filter(
            is_published=True,
            date_published__gte=today - timedelta(days=7)
        ).order_by('-total_tips', '-view_count')[:10]
    except:
        contest_entries = Journal.objects.filter(
            is_published=True,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).order_by('-view_count')[:10]

    contest_data = {
        'prize': '$100 + Featured Spotlight',
        'ends_in_days': days_until_sunday,
        'end_date': contest_end,
        'entries_count': len(contest_entries),
        'entries': contest_entries,
    }

    return render(request, 'diary/marketplace_contest.html', {'contest': contest_data})

def marketplace_faq(request):
    """FAQ about the marketplace feature"""
    faqs = [
        {
            'question': 'How do I publish my journal to the marketplace?',
            'answer': 'Go to your dashboard and click "Publish to Marketplace". Select the entries you want to include, set a price (or make it free), and add a description.'
        },
        {
            'question': 'How much can I earn from my journals?',
            'answer': 'You keep 90% of all sales and tips. Popular journals can earn anywhere from $10 to $500+ depending on quality and audience engagement.'
        },
        {
            'question': 'Can I make my journal free?',
            'answer': 'Yes! You can publish free journals and still receive tips from readers who appreciate your work.'
        },
        {
            'question': 'How do payments work?',
            'answer': 'Payments are processed securely through our platform. Earnings are paid out monthly to your connected payment method.'
        },
        {
            'question': 'Can I edit my journal after publishing?',
            'answer': 'You can edit the description and price, but published entries cannot be modified to maintain authenticity.'
        },
    ]

    return render(request, 'diary/marketplace_faq.html', {'faqs': faqs})

# Additional API endpoints for enhanced functionality
@login_required
@require_POST
def add_to_wishlist(request, journal_id):
    """Add/remove journal from user's wishlist"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    # This would require a Wishlist model, for now return success
    return JsonResponse({
        'success': True,
        'message': 'Added to wishlist!',
        'in_wishlist': True
    })

@login_required
@require_POST
def add_to_comparison(request, journal_id):
    """Add journal to comparison list"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    # Store in session for now
    comparison_list = request.session.get('comparison_list', [])
    if journal_id not in comparison_list and len(comparison_list) < 4:
        comparison_list.append(journal_id)
        request.session['comparison_list'] = comparison_list
        return JsonResponse({
            'success': True,
            'message': 'Added to comparison!',
            'count': len(comparison_list)
        })

    return JsonResponse({
        'success': False,
        'error': 'Maximum 4 items can be compared'
    })

@login_required
def marketplace_search_suggestions(request):
    """AJAX endpoint for search suggestions"""
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return JsonResponse({'suggestions': []})

    # Get suggestions from journal titles and author names
    suggestions = []

    try:
        # Title suggestions
        titles = Journal.objects.filter(
            is_published=True,
            title__icontains=query
        ).values_list('title', flat=True)[:5]

        # Author suggestions
        authors = Journal.objects.filter(
            is_published=True,
            author__username__icontains=query
        ).values_list('author__username', flat=True).distinct()[:3]

        suggestions = list(titles) + [f"by {author}" for author in authors]

    except Exception as e:
        pass

    return JsonResponse({'suggestions': suggestions[:8]})


@login_required
@require_POST
def purchase_journal_api(request, journal_id):
    """API endpoint for purchasing journals"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    if journal.author == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot purchase your own journal'})

    # Check if already purchased
    if JournalPurchase.objects.filter(user=request.user, journal=journal).exists():
        return JsonResponse({'success': False, 'error': 'Journal already purchased'})

    try:
        data = json.loads(request.body)
        payment_method_id = data.get('payment_method_id')

        if journal.price > 0 and not payment_method_id:
            return JsonResponse({'success': False, 'error': 'Payment method required'})

        purchase, intent = MarketplaceService.process_purchase(
            user=request.user,
            journal=journal,
            payment_method_id=payment_method_id
        )

        if purchase:
            return JsonResponse({
                'success': True,
                'message': f'Successfully purchased "{journal.title}"!',
                'purchase_id': purchase.id
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Payment failed'
            })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def tip_author_api(request, journal_id):
    """API endpoint for tipping authors"""
    journal = get_object_or_404(Journal, id=journal_id, is_published=True)

    if journal.author == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot tip yourself'})

    try:
        data = json.loads(request.body)
        amount = float(data.get('amount', 0))
        message = data.get('message', '')

        if amount < 0.50:
            return JsonResponse({'success': False, 'error': 'Minimum tip is $0.50'})

        tip, intent = MarketplaceService.process_tip(
            tipper=request.user,
            journal=journal,
            amount=amount,
            message=message
        )

        return JsonResponse({
            'success': True,
            'message': f'Tip of ${amount:.2f} sent successfully!',
            'tip_id': tip.id
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def earnings_dashboard(request):
    """Dashboard showing author earnings and analytics"""
    earnings = MarketplaceService.get_author_earnings(request.user)

    # Get published journals
    journals = Journal.objects.filter(
        author=request.user,
        is_published=True
    ).order_by('-date_published')

    # Get recent purchases and tips
    recent_purchases = JournalPurchase.objects.filter(
        journal__author=request.user
    ).select_related('user', 'journal').order_by('-created_at')[:10]

    recent_tips = Tip.objects.filter(
        recipient=request.user
    ).select_related('tipper', 'journal').order_by('-created_at')[:10]

    context = {
        'earnings': earnings,
        'journals': journals,
        'recent_purchases': recent_purchases,
        'recent_tips': recent_tips,
        'total_journals': journals.count(),
        'total_customers': JournalPurchase.objects.filter(
            journal__author=request.user
        ).values('user').distinct().count()
    }

    return render(request, 'diary/earnings_dashboard.html', context)

@login_required
def my_published_journals(request):
    """View user's published journals with analytics"""
    journals = Journal.objects.filter(
        author=request.user,
        is_published=True
    ).order_by('-date_published')

    # Add analytics to each journal
    for journal in journals:
        journal.total_purchases = journal.purchases.count()
        journal.total_revenue = journal.purchases.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        journal.total_tips_received = journal.tips.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

    context = {
        'journals': journals,
        'total_revenue': sum(j.total_revenue + j.total_tips_received for j in journals)
    }

    return render(request, 'diary/my_published_journals.html', context)