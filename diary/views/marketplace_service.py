import stripe
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from ..models import Journal, JournalEntry, JournalPurchase, Tip, Entry
from django.db import models
from django.db.models import Sum, Min, Max

# Set up Stripe
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', 'sk_test_...')

class MarketplaceService:
    """Service class for handling marketplace operations"""

    @staticmethod
    def get_author_earnings(user):
        """Get total earnings for an author"""
        total_sales = JournalPurchase.objects.filter(
            journal__author=user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        total_tips = Tip.objects.filter(
            recipient=user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Platform takes 10% of sales, 5% of tips
        sales_after_fees = total_sales * Decimal('0.90')
        tips_after_fees = total_tips * Decimal('0.95')

        return {
            'total_gross': total_sales + total_tips,
            'total_net': sales_after_fees + tips_after_fees,
            'total_sales': total_sales,
            'total_tips': total_tips,
            'platform_fees': (total_sales * Decimal('0.10')) + (total_tips * Decimal('0.05'))
        }

    @staticmethod
    def publish_entries_as_journal(user, entry_ids, title, description, price=0.00, cover_image=None):
        """Publish selected diary entries as a journal"""
        with transaction.atomic():
            # Create the journal
            journal = Journal.objects.create(
                title=title,
                description=description,
                author=user,
                price=Decimal(str(price)),
                is_published=True,
                date_published=timezone.now(),
                privacy_setting='public',
                cover_image=cover_image
            )

            # Add selected entries
            entries = Entry.objects.filter(id__in=entry_ids, user=user)
            for entry in entries:
                JournalEntry.objects.create(
                    journal=journal,
                    title=entry.title,
                    content=entry.content,
                    entry_date=entry.created_at.date(),
                    is_included=True
                )

                # Mark original entry as published
                entry.published_in_journal = journal
                entry.save()

            # Update journal metadata
            if entries.exists():
                dates = entries.aggregate(
                    first=Min('created_at'),
                    last=Max('created_at')
                )
                journal.first_entry_date = dates['first'].date() if dates['first'] else None
                journal.last_entry_date = dates['last'].date() if dates['last'] else None
                journal.save()

            journal.update_cached_counts()

            return journal

    @staticmethod
    def process_purchase(user, journal, payment_method_id=None):
        """Process a journal purchase using Stripe"""
        if journal.price <= 0:
            # Free journal - just create purchase record
            purchase = JournalPurchase.objects.create(
                user=user,
                journal=journal,
                amount=Decimal('0.00')
            )
            return purchase, None

        try:
            # Create Stripe payment intent
            intent = stripe.PaymentIntent.create(
                amount=int(journal.price * 100),  # Convert to cents
                currency='usd',
                payment_method=payment_method_id,
                confirm=True,
                metadata={
                    'journal_id': journal.id,
                    'user_id': user.id,
                    'author_id': journal.author.id
                }
            )

            if intent.status == 'succeeded':
                # Create purchase record
                purchase = JournalPurchase.objects.create(
                    user=user,
                    journal=journal,
                    amount=journal.price
                )

                # Update author earnings (take 10% platform fee)
                author_earnings = journal.price * Decimal('0.90')
                journal.total_tips += author_earnings
                journal.save()

                return purchase, intent
            else:
                return None, intent

        except stripe.error.StripeError as e:
            raise Exception(f"Payment failed: {str(e)}")

    @staticmethod
    def process_tip(tipper, journal, amount, message=""):
        """Process a tip to a journal author"""
        try:
            # Create Stripe payment intent for tip
            intent = stripe.PaymentIntent.create(
                amount=int(Decimal(str(amount)) * 100),  # Convert to cents
                currency='usd',
                metadata={
                    'type': 'tip',
                    'journal_id': journal.id,
                    'tipper_id': tipper.id,
                    'recipient_id': journal.author.id
                }
            )

            # Create tip record
            tip = Tip.objects.create(
                journal=journal,
                tipper=tipper,
                recipient=journal.author,
                amount=Decimal(str(amount)),
                transaction_id=intent.id
            )

            return tip, intent

        except stripe.error.StripeError as e:
            raise Exception(f"Tip processing failed: {str(e)}")