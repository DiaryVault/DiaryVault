# management/commands/update_marketplace_stats.py
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Avg
from diary.models import Journal, User, JournalEntry, Tip

class Command(BaseCommand):
    help = 'Update marketplace statistics and rankings'

    def handle(self, *args, **options):
        self.stdout.write('Updating marketplace statistics...')

        # Update journal popularity scores
        journals = Journal.objects.filter(is_published=True)

        for journal in journals:
            # Calculate popularity based on views, likes, tips, and recency
            popularity_score = (
                journal.view_count * 0.1 +
                journal.likes.count() * 2 +
                float(journal.total_tips) * 5 +
                journal.entries.count() * 0.5
            )

            # Boost recent journals
            days_since_published = (timezone.now().date() - journal.date_published.date()).days
            if days_since_published < 30:
                popularity_score *= 1.5
            elif days_since_published < 90:
                popularity_score *= 1.2

            journal.popularity_score = popularity_score
            journal.save(update_fields=['popularity_score'])

        # Update staff picks (top 10% by popularity)
        top_journals = journals.order_by('-popularity_score')[:max(1, len(journals) // 10)]

        # Reset all staff picks
        Journal.objects.filter(is_staff_pick=True).update(is_staff_pick=False)

        # Set new staff picks
        for journal in top_journals:
            journal.is_staff_pick = True
            journal.save(update_fields=['is_staff_pick'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Updated statistics for {journals.count()} journals. '
                f'{top_journals.count()} staff picks selected.'
            )
        )


# management/commands/generate_bestsellers.py
import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from diary.models import Journal, JournalPurchase, JournalLike, Tip, User

class Command(BaseCommand):
    help = 'Generate bestseller data for premium journals'

    def add_arguments(self, parser):
        parser.add_argument(
            '--boost-sales',
            action='store_true',
            help='Artificially boost sales for some premium journals'
        )

    def handle(self, *args, **options):
        premium_journals = Journal.objects.filter(price__gt=0, is_published=True)
        users = list(User.objects.all())

        if not premium_journals.exists():
            self.stdout.write(self.style.ERROR('No premium journals found.'))
            return

        self.stdout.write(f'Generating bestseller data for {premium_journals.count()} premium journals...')

        for journal in premium_journals:
            if options['boost_sales']:
                # Create more realistic sales patterns
                base_sales = random.randint(10, 200)

                # Create purchases
                buyers = random.sample(users, min(base_sales, len(users)))
                for buyer in buyers:
                    if buyer != journal.author:
                        JournalPurchase.objects.get_or_create(
                            user=buyer,
                            journal=journal,
                            defaults={'amount': journal.price}
                        )

                # Create additional likes for popular journals
                additional_likes = random.randint(20, 100)
                likers = random.sample(users, min(additional_likes, len(users)))
                for liker in likers:
                    if liker != journal.author:
                        JournalLike.objects.get_or_create(
                            user=liker,
                            journal=journal
                        )

                # Create tips
                tip_count = random.randint(5, 30)
                tippers = random.sample(users, min(tip_count, len(users)))
                for tipper in tippers:
                    if tipper != journal.author:
                        amount = Decimal(str(random.choice([1.00, 2.00, 5.00, 10.00])))
                        Tip.objects.create(
                            journal=journal,
                            tipper=tipper,
                            recipient=journal.author,
                            amount=amount
                        )

                # Update total tips
                total_tips = Tip.objects.filter(journal=journal).aggregate(
                    total=models.Sum('amount')
                )['total'] or Decimal('0.00')
                journal.total_tips = total_tips
                journal.save(update_fields=['total_tips'])

            # Update cached counts
            journal.update_cached_counts()

        self.stdout.write(self.style.SUCCESS('Generated bestseller data successfully!'))


# management/commands/create_featured_content.py
import random
from django.core.management.base import BaseCommand
from diary.models import Journal, JournalTag

class Command(BaseCommand):
    help = 'Create featured content for the marketplace homepage'

    def handle(self, *args, **options):
        self.stdout.write('Creating featured content...')

        # Select top journals for featuring
        top_journals = Journal.objects.filter(
            is_published=True
        ).order_by('-popularity_score', '-total_tips', '-view_count')[:20]

        if not top_journals.exists():
            self.stdout.write(self.style.ERROR('No published journals found.'))
            return

        # Clear existing featured status
        Journal.objects.filter(featured=True).update(featured=False)

        # Set one journal as main featured
        main_featured = top_journals.first()
        main_featured.featured = True
        main_featured.save(update_fields=['featured'])

        # Mark top 10 as staff picks if they aren't already
        staff_picks = top_journals[:10]
        for journal in staff_picks:
            if not journal.is_staff_pick:
                journal.is_staff_pick = True
                journal.save(update_fields=['is_staff_pick'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Featured content created! Main featured: "{main_featured.title}"'
            )
        )


# management/commands/simulate_marketplace_activity.py
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from diary.models import Journal, User, JournalLike, JournalPurchase, Tip, JournalReview
from decimal import Decimal

class Command(BaseCommand):
    help = 'Simulate realistic marketplace activity (views, purchases, likes, etc.)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days of activity to simulate'
        )

    def handle(self, *args, **options):
        days = options['days']
        journals = list(Journal.objects.filter(is_published=True))
        users = list(User.objects.all())

        if not journals or not users:
            self.stdout.write(self.style.ERROR('Need journals and users to simulate activity.'))
            return

        self.stdout.write(f'Simulating {days} days of marketplace activity...')

        for day in range(days):
            current_date = timezone.now() - timedelta(days=day)

            # Simulate daily views (each journal gets 5-50 views per day)
            for journal in journals:
                daily_views = random.randint(5, 50)
                journal.view_count += daily_views

            # Simulate purchases (1-5 purchases per day across all premium journals)
            premium_journals = [j for j in journals if j.price > 0]
            daily_purchases = random.randint(1, 5)

            for _ in range(daily_purchases):
                journal = random.choice(premium_journals)
                buyer = random.choice([u for u in users if u != journal.author])

                JournalPurchase.objects.get_or_create(
                    user=buyer,
                    journal=journal,
                    defaults={'amount': journal.price}
                )

            # Simulate likes (10-30 likes per day across all journals)
            daily_likes = random.randint(10, 30)

            for _ in range(daily_likes):
                journal = random.choice(journals)
                liker = random.choice([u for u in users if u != journal.author])

                JournalLike.objects.get_or_create(
                    user=liker,
                    journal=journal
                )

            # Simulate tips (1-3 tips per day)
            daily_tips = random.randint(1, 3)

            for _ in range(daily_tips):
                journal = random.choice(journals)
                tipper = random.choice([u for u in users if u != journal.author])
                amount = Decimal(str(random.choice([1.00, 2.00, 3.00, 5.00, 10.00])))

                Tip.objects.create(
                    journal=journal,
                    tipper=tipper,
                    recipient=journal.author,
                    amount=amount
                )

            # Simulate reviews (1-2 reviews per day)
            daily_reviews = random.randint(1, 2)

            for _ in range(daily_reviews):
                journal = random.choice(journals)
                reviewer = random.choice([u for u in users if u != journal.author])

                # Skip if user already reviewed this journal
                if JournalReview.objects.filter(user=reviewer, journal=journal).exists():
                    continue

                rating = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 15, 35, 35])[0]
                review_texts = {
                    5: "Outstanding journal! Really inspiring.",
                    4: "Great read, highly recommend.",
                    3: "Good journal with interesting insights.",
                    2: "It was okay, not my favorite.",
                    1: "Didn't enjoy this one."
                }

                JournalReview.objects.create(
                    user=reviewer,
                    journal=journal,
                    rating=rating,
                    review_text=review_texts[rating]
                )

        # Update all journal statistics
        for journal in journals:
            # Update total tips
            total_tips = Tip.objects.filter(journal=journal).aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0.00')
            journal.total_tips = total_tips
            journal.save()

            # Update cached counts
            journal.update_cached_counts()
            journal.calculate_popularity()

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully simulated {days} days of marketplace activity!'
            )
        )


# management/commands/export_marketplace_data.py
import csv
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Avg
from diary.models import Journal, User, JournalTag

class Command(BaseCommand):
    help = 'Export marketplace data to CSV for analysis'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='marketplace_data.csv',
            help='Output CSV filename'
        )

    def handle(self, *args, **options):
        filename = options['output']

        self.stdout.write(f'Exporting marketplace data to {filename}...')

        journals = Journal.objects.filter(is_published=True).annotate(
            like_count=Count('likes'),
            review_count=Count('reviews'),
            purchase_count=Count('purchases')
        )

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Write header
            writer.writerow([
                'Title', 'Author', 'Category', 'Price', 'Free', 'Staff Pick',
                'View Count', 'Like Count', 'Review Count', 'Purchase Count',
                'Total Tips', 'Entry Count', 'Popularity Score', 'Published Date'
            ])

            # Write data
            for journal in journals:
                categories = ', '.join([tag.name for tag in journal.marketplace_tags.all()])

                writer.writerow([
                    journal.title,
                    journal.author.username,
                    categories,
                    float(journal.price),
                    journal.price == 0,
                    journal.is_staff_pick,
                    journal.view_count,
                    journal.like_count,
                    journal.review_count,
                    journal.purchase_count,
                    float(journal.total_tips),
                    journal.entries.count(),
                    journal.popularity_score,
                    journal.date_published.date()
                ])

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully exported {journals.count()} journals to {filename}'
            )
        )


# management/commands/cleanup_marketplace.py
from django.core.management.base import BaseCommand
from django.db.models import Count
from diary.models import Journal, JournalTag, User

class Command(BaseCommand):
    help = 'Clean up marketplace data (remove empty categories, inactive users, etc.)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write('DRY RUN - No data will be deleted')

        # Find empty categories
        empty_categories = JournalTag.objects.annotate(
            journal_count=Count('journal')
        ).filter(journal_count=0)

        # Find users with no journals
        inactive_users = User.objects.annotate(
            journal_count=Count('journals')
        ).filter(journal_count=0, is_staff=False, is_superuser=False)

        # Find unpublished journals older than 30 days
        old_unpublished = Journal.objects.filter(
            is_published=False,
            created_at__lt=timezone.now() - timedelta(days=30)
        )

        self.stdout.write(f'Empty categories: {empty_categories.count()}')
        self.stdout.write(f'Inactive users: {inactive_users.count()}')
        self.stdout.write(f'Old unpublished journals: {old_unpublished.count()}')

        if not dry_run:
            # Delete empty categories
            deleted_categories = empty_categories.delete()[0]

            # Delete old unpublished journals
            deleted_journals = old_unpublished.delete()[0]

            self.stdout.write(
                self.style.SUCCESS(
                    f'Cleaned up {deleted_categories} empty categories and '
                    f'{deleted_journals} old unpublished journals'
                )
            )
        else:
            self.stdout.write('Use --dry-run=False to actually perform cleanup')
