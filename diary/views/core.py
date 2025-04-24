from datetime import timedelta
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.views import LoginView
from django.contrib.auth import views as auth_views

from ..models import (
    Entry, Tag, SummaryVersion, LifeChapter, Biography,
    UserInsight, EntryTag, UserPreference
)
from ..forms import EntryForm, SignUpForm, LifeChapterForm
from ..services.ai_service import AIService

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
