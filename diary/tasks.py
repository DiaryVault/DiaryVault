from celery import shared_task
from django.contrib.auth.models import User
from .views.marketplace_service import MarketplaceService

@shared_task
def process_monthly_payouts():
    """Process monthly payouts to authors"""
    authors = User.objects.filter(
        journals__is_published=True
    ).distinct()

    for author in authors:
        earnings = MarketplaceService.get_author_earnings(author)
        if earnings['total_net'] >= 50:  # Minimum payout threshold
            # Process payout
            # This would integrate with Stripe Connect or similar
            pass

@shared_task
def update_journal_popularity_scores():
    """Update popularity scores for all journals"""
    from .models import Journal

    journals = Journal.objects.filter(is_published=True)
    for journal in journals:
        journal.calculate_popularity()
