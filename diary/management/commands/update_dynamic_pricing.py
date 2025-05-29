from django.core.management.base import BaseCommand
from diary.models import Journal
from diary.services.advanced_marketplace_service import MarketplaceEnhancementService
from decimal import Decimal

class Command(BaseCommand):
    help = 'Update dynamic pricing for all journals based on market demand'

    def handle(self, *args, **options):
        journals = Journal.objects.filter(is_published=True)

        updated_count = 0
        for journal in journals:
            pricing_data = MarketplaceEnhancementService.calculate_dynamic_pricing(
                journal, journal.price
            )

            # Only suggest price changes if significant difference
            price_diff = abs(pricing_data['suggested_price'] - journal.price)
            if price_diff >= Decimal('0.50'):  # At least 50 cent difference
                self.stdout.write(
                    f"Journal '{journal.title}': "
                    f"Current: ${journal.price}, "
                    f"Suggested: ${pricing_data['suggested_price']} "
                    f"({pricing_data['reasoning']})"
                )
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Analyzed {journals.count()} journals, '
                f'found {updated_count} pricing optimization opportunities'
            )
        )
