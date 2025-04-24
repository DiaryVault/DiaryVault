from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User

def marketplace_view(request):
    """Main marketplace view showing featured journals"""
    # Later, you can fetch actual journal data from your database
    # For now, using mock data

    # Sample featured journals (just for display)
    featured_journals = [
        {
            'id': 1,
            'title': 'Around the World in 80 Days',
            'author': 'adventurer',
            'description': 'A travel journal chronicling adventures across six continents and fifteen countries.',
            'tags': ['Travel', 'Adventure', 'Photography'],
            'likes': 872,
            'views': 4200,
            'tips': 4520,
            'cover_image': 'https://images.unsplash.com/photo-1541410965313-d53b3c16ef17',
            'rank': 1
        },
        {
            'id': 2,
            'title': 'Mindfulness Journey',
            'author': 'mindful_me',
            'description': 'A year of daily meditations and mindfulness practices documented with reflections.',
            'tags': ['Mindfulness', 'Wellness', 'Self-Care'],
            'likes': 621,
            'views': 3180,
            'tips': 3180,
            'cover_image': 'https://images.unsplash.com/photo-1533090161767-e6ffed986c88',
            'rank': 2
        },
        {
            'id': 3,
            'title': 'From Novice to Engineer',
            'author': 'code_chronicles',
            'description': 'A coding journey documenting the path from complete beginner to professional software engineer.',
            'tags': ['Technology', 'Coding', 'Career'],
            'likes': 512,
            'views': 2845,
            'tips': 2845,
            'cover_image': 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97',
            'rank': 3
        },
    ]

    context = {
        'featured_journals': featured_journals,
        'filter_type': 'popular'  # Default filter
    }

    return render(request, 'diary/marketplace.html', context)

@login_required
def marketplace_publish(request):
    """View for publishing a journal to the marketplace"""
    # Placeholder for now
    if request.method == 'POST':
        # Handle publishing logic later
        messages.success(request, "Your journal has been published to the marketplace!")
        return redirect('marketplace')

    return render(request, 'marketplace_publish.html')

def marketplace_monetization(request):
    """Information page about monetization"""
    return render(request, 'marketplace_monetization.html')

def marketplace_contest(request):
    """Weekly contest page"""
    # Sample contest data
    contest_data = {
        'prize': '$100 + Featured Spotlight',
        'ends_in_days': 3,
        'entries_count': 157
    }

    return render(request, 'marketplace_contest.html', {'contest': contest_data})

def marketplace_faq(request):
    """FAQ about the marketplace feature"""
    return render(request, 'marketplace_faq.html')

def marketplace_journal_detail(request, journal_id):
    """View for a single published journal"""
    # This is a placeholder - later you'll fetch the actual journal by ID
    journal = {
        'id': journal_id,
        'title': 'Sample Journal',
        'description': 'This is a placeholder journal entry.',
        'author': 'username',
        'entries': []  # Would contain actual entries
    }

    return render(request, 'marketplace_journal_detail.html', {'journal': journal})

def marketplace_author_profile(request, username):
    """View for an author's profile"""
    # This is a placeholder - later you'll fetch the actual user
    try:
        user = User.objects.get(username=username)
        # For now, just basic user info - later you'll add journals
        context = {
            'profile_user': user,
            'journals': []  # Would contain user's journals
        }
        return render(request, 'marketplace_author_profile.html', context)
    except User.DoesNotExist:
        messages.error(request, "Author not found")
        return redirect('marketplace')
