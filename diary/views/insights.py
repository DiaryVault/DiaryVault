from collections import Counter
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import Entry, Tag, UserInsight
from ..utils.analytics import get_mood_emoji, get_tag_color, mood_to_numeric_value

logger = logging.getLogger(__name__)

@login_required
def insights(request):
    """View for showing AI-generated insights about the user's journal entries."""

    # Handle regenerating insights
    if request.method == 'POST' and 'regenerate_insights' in request.POST:
        # Delete existing insights for this user
        UserInsight.objects.filter(user=request.user).delete()

        # Generate new insights using AIService
        from ..services.ai_service import AIService
        AIService.generate_insights(request.user)

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
    from django.db.models import Count

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
    from django.utils import timezone
    from datetime import timedelta

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
