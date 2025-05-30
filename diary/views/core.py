from datetime import timedelta
import logging
import json
import random

from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.views import LoginView
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Sum, F, Q
from django.core.cache import cache
from django.conf import settings
from django.urls import reverse_lazy, reverse


from ..models import (
    Entry, Tag, SummaryVersion, LifeChapter, Biography,
    UserInsight, EntryTag, UserPreference, Journal, JournalTag
)
from ..forms import EntryForm, SignUpForm, LifeChapterForm
from ..services.ai_service import AIService

from allauth.account.utils import get_next_redirect_url
from allauth.account.views import LoginView as AllauthLoginView, SignupView as AllauthSignupView


logger = logging.getLogger(__name__)

def home(request):
    """Enhanced landing page with marketplace integration"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    # Try to get data from cache first (cache for 15 minutes)
    cache_key = 'home_page_data'
    cached_data = cache.get(cache_key)

    if cached_data:
        context = cached_data
    else:
        context = get_home_context()
        cache.set(cache_key, context, 900)  # Cache for 15 minutes

    return render(request, 'diary/home.html', context)

def get_home_context():
    """Get all context data for home page"""
    # Get featured journals for marketplace preview (now 18)
    featured_journals = get_featured_journals()

    # Get marketplace statistics
    marketplace_stats = get_marketplace_stats()

    # Get current date
    current_date = timezone.now().strftime('%B %d, %Y')

    context = {
        'featured_journals': featured_journals,
        'marketplace_stats': marketplace_stats,
        'current_date': current_date,
        'has_conversation': False,  # For chat area
        'conversation': [],  # Empty conversation for new users
    }

    return context

def get_featured_journals():
    """Get featured journals for homepage display - now returns 18 instead of 6"""
    try:
        # Get published journals with good engagement
        base_query = Journal.objects.filter(
            is_published=True,
        ).select_related('author').prefetch_related(
            'marketplace_tags',  # This should work with your JournalTag relationship
            'likes',
            'entries'
        ).annotate(
            like_count=Count('likes'),
            entry_count=Count('entries'),
            view_count_annotated=F('view_count')
        )

        # Strategy: Get a diverse mix of 18 journals
        featured_journals = []
        featured_ids = set()

        # 1. Get staff picks first (up to 6)
        staff_picks = base_query.filter(is_staff_pick=True)[:6]
        for journal in staff_picks:
            if journal.id not in featured_ids and len(featured_journals) < 20:
                featured_journals.append(journal)
                featured_ids.add(journal.id)

        # 2. Get high-performing journals (up to 6 more)
        popular_journals = base_query.filter(
            Q(like_count__gte=5) | Q(view_count__gte=100)
        ).exclude(id__in=featured_ids).order_by('-like_count', '-view_count')[:6]

        for journal in popular_journals:
            if journal.id not in featured_ids and len(featured_journals) < 20:
                featured_journals.append(journal)
                featured_ids.add(journal.id)

        # 3. Get recent quality journals (up to 6 more)
        recent_journals = base_query.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=30),
            like_count__gte=1
        ).exclude(id__in=featured_ids).order_by('-created_at')[:6]

        for journal in recent_journals:
            if journal.id not in featured_ids and len(featured_journals) < 20:
                featured_journals.append(journal)
                featured_ids.add(journal.id)

        # 4. If we still need more journals, get any published journals
        if len(featured_journals) < 20:
            remaining_needed = 20 - len(featured_journals)
            remaining_journals = base_query.exclude(
                id__in=featured_ids
            ).order_by('-created_at')[:remaining_needed]

            featured_journals.extend(remaining_journals)

        # 5. Alternative approach if we still don't have 18 journals
        # Fill with random selection to ensure we always have content
        if len(featured_journals) < 20:
            all_available = base_query.exclude(id__in=featured_ids).order_by('?')
            remaining_needed = 20 - len(featured_journals)
            random_journals = all_available[:remaining_needed]
            featured_journals.extend(random_journals)

        # Add calculated fields for template
        for journal in featured_journals:
            # Calculate total tips (if you have a tips model)
            journal.total_tips = calculate_journal_earnings(journal)

            # Ensure view_count exists
            if not hasattr(journal, 'view_count') or journal.view_count is None:
                journal.view_codeunt = 0

        # Shuffle the final list for variety on each page load
        import random
        random.shuffle(featured_journals)

        # Return exactly 18 journals (or whatever we have)
        return featured_journals[:20]

    except Exception as e:
        # Fallback: return empty list if there's any error
        print(f"Error getting featured journals: {e}")
        return []

def calculate_journal_earnings(journal):
    """Calculate total earnings for a journal - enhanced for more realistic demo data"""
    try:
        # If you have a tips/payments model, calculate here
        if hasattr(journal, 'payments'):
            return float(journal.payments.aggregate(
                total=Sum('amount')
            )['total'] or 0)
        else:
            # Enhanced demo values based on journal popularity and age
            like_count = getattr(journal, 'like_count', 0)
            view_count = getattr(journal, 'view_count', 0)
            entry_count = getattr(journal, 'entry_count', 0)

            # Calculate days since creation for aging factor
            days_old = (timezone.now() - journal.created_at).days if hasattr(journal, 'created_at') else 30

            # More sophisticated earning calculation
            base_score = (like_count * 10) + (view_count * 0.1) + (entry_count * 5)
            age_multiplier = min(days_old / 30, 3)  # Cap at 3x for very old journals

            if base_score > 500:
                earnings = random.uniform(1000, 5000) * age_multiplier
            elif base_score > 100:
                earnings = random.uniform(200, 1000) * age_multiplier
            elif base_score > 20:
                earnings = random.uniform(25, 200) * age_multiplier
            else:
                # Some journals have no earnings
                earnings = 0 if random.random() < 0.4 else random.uniform(5, 25)

            return round(earnings, 2)
    except:
        return 0

def get_marketplace_stats():
    """Get overall marketplace statistics - enhanced for 18+ journals"""
    try:
        # Import models with fallback
        try:
            from ..models import Journal
            from django.contrib.auth import get_user_model
            User = get_user_model()
        except ImportError:
            try:
                from ..models import Journal
                from django.contrib.auth import get_user_model
                User = get_user_model()
            except ImportError:
                from diary.models import Journal
                from django.contrib.auth.models import User

        # Get real stats
        total_journals = Journal.objects.filter(is_published=True).count()
        total_authors = User.objects.filter(
            journals__is_published=True
        ).distinct().count()
        free_journals = Journal.objects.filter(
            is_published=True,
            price=0
        ).count()

        # Calculate total earnings from all journals
        all_journals = Journal.objects.filter(is_published=True)
        total_earnings = sum(calculate_journal_earnings(j) for j in all_journals)

        # Calculate total entries
        total_entries = 0
        for journal in all_journals:
            total_entries += journal.entries.count()

        stats = {
            'total_journals': total_journals,
            'total_authors': total_authors,
            'total_earnings': total_earnings,
            'total_entries': total_entries,
            'categories_count': 12,  # Update this based on your categories
            'free_journals': free_journals,
        }

        # Enhance stats if numbers are too low for a good demo
        if stats['total_journals'] < 18:
            stats.update({
                'total_journals': random.randint(150, 300),
                'total_authors': random.randint(75, 150),
                'total_earnings': random.randint(50000, 200000),
                'total_entries': random.randint(1000, 5000),
                'free_journals': random.randint(50, 120)
            })

        return stats

    except Exception as e:
        # Fallback demo stats for a thriving marketplace
        return {
            'total_journals': random.randint(200, 400),
            'total_authors': random.randint(100, 200),
            'total_earnings': random.randint(75000, 250000),
            'total_entries': random.randint(2000, 8000),
            'categories_count': 12,
            'free_journals': random.randint(80, 150),
        }

def signup(request):
    """
    User registration view with feature tracking
    """
    # Track which feature led the user to signup
    feature = request.GET.get('feature', None)

    # Feature information for highlighting on signup page
    feature_data = {
        'journal': {
            'title': 'Journal Your Thoughts',
            'description': 'Create beautiful journal entries powered by AI. Track your daily experiences, emotions, and reflections.',
            'icon': 'pencil'
        },
        'library': {
            'title': 'Browse Your Memory Library',
            'description': 'Organize and explore your journal entries by time period, mood, and themes.',
            'icon': 'book'
        },
        'insights': {
            'title': 'Discover Personal Insights',
            'description': 'Get AI-powered analytics about your writing patterns, mood trends, and personal growth.',
            'icon': 'chart'
        },
        'biography': {
            'title': 'Create Your Life Story',
            'description': 'DiaryVault transforms your journal entries into beautiful chapter-based biographies.',
            'icon': 'document'
        }
    }

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            # Create and save the user
            user = form.save()

            # Log the user in
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            login(request, user)

            # Create initial user preferences
            try:
                from ..models import JournalPreferences
                JournalPreferences.objects.create(user=user)
            except Exception as e:
                print(f"Error creating preferences: {e}")

            # Direct the user to the appropriate page based on the feature
            # that brought them to signup
            redirect_url = 'dashboard'  # Default redirect

            if feature == 'journal':
                redirect_url = 'new_entry'
                messages.success(request, "Your account has been created! Start your first journal entry.")
            elif feature == 'library':
                redirect_url = 'library'
                messages.success(request, "Your account has been created! Explore your journal library.")
            elif feature == 'insights':
                redirect_url = 'insights'
                messages.success(request, "Your account has been created! Discover insights about your journaling.")
            elif feature == 'biography':
                redirect_url = 'biography'
                messages.success(request, "Your account has been created! Start building your biography.")
            else:
                messages.success(request, "Welcome to DiaryVault! Your account has been created successfully.")

            return redirect(redirect_url)
        else:
            # If form is invalid, re-render with errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = SignUpForm()

    context = {
        'form': form,
        'feature': feature,
        'feature_info': feature_data.get(feature, None)
    }

    return render(request, 'diary/signup.html', context)

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

def custom_login(request):
    """Custom login view that handles save_after_login flag"""
    # Store a flag in session if this is a post-save login
    if 'save_after_login' in request.GET:
        request.session['save_after_login'] = True

    # Use Django's built-in login view
    return auth_views.LoginView.as_view(template_name='diary/login.html')(request)

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
                    from ..utils.analytics import auto_generate_tags
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

# ============================================================================
# API Views for JavaScript integration
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def track_journal_view(request, journal_id):
    """Track journal view for analytics"""
    try:
        # Import models with fallback
        try:
            from ..models import Journal
        except ImportError:
            try:
                from ..models import Journal
            except ImportError:
                from diary.models import Journal

        journal = Journal.objects.get(id=journal_id, is_published=True)

        # Update view count atomically
        Journal.objects.filter(id=journal_id).update(
            view_count=F('view_count') + 1
        )

        return JsonResponse({'success': True})

    except Journal.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Journal not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_http_methods(["POST"])
def add_to_wishlist(request):
    """Add journal to user's wishlist"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Login required'})

    try:
        # Import models with fallback
        try:
            from ..models import Journal
        except ImportError:
            try:
                from ..models import Journal
            except ImportError:
                from diary.models import Journal

        data = json.loads(request.body)
        journal_id = data.get('journal_id')

        journal = Journal.objects.get(id=journal_id, is_published=True)

        # Create or get wishlist relationship
        # Adjust this based on your wishlist model structure
        if hasattr(request.user, 'wishlist'):
            request.user.wishlist.add(journal)
        else:
            # If you have a separate Wishlist model
            try:
                from ..models import Wishlist
            except ImportError:
                try:
                    from ..models import Wishlist
                except ImportError:
                    from diary.models import Wishlist

            Wishlist.objects.get_or_create(
                user=request.user,
                journal=journal
            )

        return JsonResponse({'success': True})

    except Journal.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Journal not found'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_http_methods(["POST"])
def remove_from_wishlist(request):
    """Remove journal from user's wishlist"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Login required'})

    try:
        # Import models with fallback
        try:
            from ..models import Journal
        except ImportError:
            try:
                from ..models import Journal
            except ImportError:
                from diary.models import Journal

        data = json.loads(request.body)
        journal_id = data.get('journal_id')

        journal = Journal.objects.get(id=journal_id)

        # Remove from wishlist
        if hasattr(request.user, 'wishlist'):
            request.user.wishlist.remove(journal)
        else:
            # If you have a separate Wishlist model
            try:
                from ..models import Wishlist
            except ImportError:
                try:
                    from ..models import Wishlist
                except ImportError:
                    from diary.models import Wishlist

            Wishlist.objects.filter(
                user=request.user,
                journal=journal
            ).delete()

        return JsonResponse({'success': True})

    except Journal.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Journal not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def journal_preview(request, journal_id):
    """Get journal preview data for quick view modal"""
    try:
        # Import models with fallback
        try:
            from ..models import Journal
        except ImportError:
            try:
                from ..models import Journal
            except ImportError:
                from diary.models import Journal

        journal = Journal.objects.select_related('author').prefetch_related(
            'marketplace_tags', 'likes', 'entries'
        ).get(id=journal_id, is_published=True)

        # Build preview data
        preview_data = {
            'success': True,
            'journal': {
                'id': journal.id,
                'title': journal.title,
                'description': journal.description or '',
                'author_name': journal.author.get_full_name() or journal.author.username,
                'cover_image': journal.cover_image.url if journal.cover_image else None,
                'price': float(journal.price) if journal.price else 0,
                'view_count': journal.view_count or 0,
                'entry_count': journal.entries.count(),
                'like_count': journal.likes.count(),
                'rating': 5.0,  # Calculate actual rating if you have reviews
                'tags': [tag.name for tag in journal.marketplace_tags.all()[:3]]
            }
        }

        return JsonResponse(preview_data)

    except Journal.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Journal not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

def marketplace_stats(request):
    """Get real-time marketplace statistics"""
    try:
        # Import models with fallback
        try:
            from ..models import Journal
        except ImportError:
            try:
                from ..models import Journal
            except ImportError:
                from diary.models import Journal

        # Get updated stats
        journals = Journal.objects.filter(is_published=True).select_related('author')

        stats_data = {
            'success': True,
            'earnings': {},
            'views': {},
            'total_journals': journals.count(),
        }

        # Add individual journal stats
        for journal in journals:
            stats_data['earnings'][str(journal.id)] = calculate_journal_earnings(journal)
            stats_data['views'][str(journal.id)] = journal.view_count or 0

        return JsonResponse(stats_data)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

class CustomLoginView(AllauthLoginView):
    """
    Custom login view that uses our custom template
    """
    # UPDATED: Use the full path from the templates directory
    template_name = 'diary/account/login.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context here
        context['page_title'] = 'Login - DiaryVault'
        return context

    def get_success_url(self):
        # Redirect to dashboard after successful login
        url = get_next_redirect_url(self.request) or reverse('dashboard')
        return url

    def form_valid(self, form):
        """Process the valid form and check for pending entries"""
        # First do the standard login process
        response = super().form_valid(form)

        # Check for pending entry in session
        pending_entry = self.request.session.get('pending_entry')
        if pending_entry:
            try:
                from ..models import Entry, Tag

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
                    try:
                        from ..utils.analytics import auto_generate_tags
                        tags = auto_generate_tags(pending_entry.get('content'), pending_entry.get('mood'))
                    except:
                        pass

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

class CustomSignupView(AllauthSignupView):
    """
    Custom signup view that uses our custom template
    """
    # Use the template you just created
    template_name = 'diary/account/signup.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context here
        context['page_title'] = 'Sign Up - DiaryVault'

        # Track which feature led the user to signup
        feature = self.request.GET.get('feature', None)
        feature_data = {
            'journal': {
                'title': 'Journal Your Thoughts',
                'description': 'Create beautiful journal entries powered by AI. Track your daily experiences, emotions, and reflections.',
                'icon': 'pencil'
            },
            'library': {
                'title': 'Browse Your Memory Library',
                'description': 'Organize and explore your journal entries by time period, mood, and themes.',
                'icon': 'book'
            },
            'insights': {
                'title': 'Discover Personal Insights',
                'description': 'Get AI-powered analytics about your writing patterns, mood trends, and personal growth.',
                'icon': 'chart'
            },
            'biography': {
                'title': 'Create Your Life Story',
                'description': 'DiaryVault transforms your journal entries into beautiful chapter-based biographies.',
                'icon': 'document'
            }
        }

        context['feature'] = feature
        context['feature_info'] = feature_data.get(feature, None)
        return context

    def get_success_url(self):
        # Get the feature parameter to redirect appropriately
        feature = self.request.GET.get('feature', None)

        if feature == 'journal':
            return reverse('new_entry')
        elif feature == 'library':
            return reverse('library')
        elif feature == 'insights':
            return reverse('insights')
        elif feature == 'biography':
            return reverse('biography')
        else:
            return reverse('dashboard')

    def form_valid(self, form):
        """Process the valid form and create user preferences"""
        response = super().form_valid(form)

        # Create initial user preferences
        try:
            UserPreference.objects.create(user=self.user)
        except Exception as e:
            logger.error(f"Error creating preferences: {e}")

        # Add success message based on feature
        feature = self.request.GET.get('feature', None)
        if feature == 'journal':
            messages.success(self.request, "Your account has been created! Start your first journal entry.")
        elif feature == 'library':
            messages.success(self.request, "Your account has been created! Explore your journal library.")
        elif feature == 'insights':
            messages.success(self.request, "Your account has been created! Discover insights about your journaling.")
        elif feature == 'biography':
            messages.success(self.request, "Your account has been created! Start building your biography.")
        else:
            messages.success(self.request, "Welcome to DiaryVault! Your account has been created successfully.")

        return response
