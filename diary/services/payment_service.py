import stripe
from django.conf import settings
from decimal import Decimal

class PaymentService:
    """Handle payment processing and payouts"""

    def __init__(self):
        stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

    def create_payment_intent(self, amount, currency='usd', metadata=None):
        """Create a Stripe payment intent"""
        return stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency=currency,
            metadata=metadata or {}
        )

    def process_payout(self, user, amount):
        """Process payout to author (requires Stripe Connect)"""
        # This would require Stripe Connect setup
        # For now, just track the payout request
        pass

    def calculate_platform_fee(self, amount, fee_percent=10):
        """Calculate platform fee"""
        return amount * Decimal(str(fee_percent / 100))
