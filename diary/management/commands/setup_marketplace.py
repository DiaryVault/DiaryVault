# management/commands/setup_marketplace.py
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Complete marketplace setup with sample data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--quick',
            action='store_true',
            help='Quick setup with minimal data'
        )
        parser.add_argument(
            '--full',
            action='store_true',
            help='Full setup with comprehensive data'
        )

    def handle(self, *args, **options):
        if options['quick']:
            self.quick_setup()
        elif options['full']:
            self.full_setup()
        else:
            self.standard_setup()

    def quick_setup(self):
        """Quick setup for development/testing"""
        self.stdout.write(self.style.SUCCESS('🚀 Quick Marketplace Setup'))
        self.stdout.write('=' * 50)

        # Create admin user if doesn't exist
        if not User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Creating admin user...')
            User.objects.create_superuser(
                'admin', 'admin@example.com', 'admin123'
            )

        # Create sample users with diary entries
        self.stdout.write('Creating sample users...')
        call_command('create_sample_users', '--count=5')

        # Populate marketplace with minimal data
        self.stdout.write('Populating marketplace...')
        call_command('populate_marketplace', '--users=5', '--journals=20')

        # Update statistics
        self.stdout.write('Updating statistics...')
        call_command('update_marketplace_stats')

        self.stdout.write(
            self.style.SUCCESS(
                '\n✅ Quick setup complete!\n'
                'Admin: admin / admin123\n'
                'Sample users: mindful_mike, sarah_traveler, etc. / testpass123\n'
                '20 journals with realistic data created!'
            )
        )

    def full_setup(self):
        """Full setup for production-like environment"""
        self.stdout.write(self.style.SUCCESS('🎯 Full Marketplace Setup'))
        self.stdout.write('=' * 50)

        # Create admin user if doesn't exist
        if not User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Creating admin user...')
            User.objects.create_superuser(
                'admin', 'admin@example.com', 'admin123'
            )

        # Create comprehensive sample users
        self.stdout.write('Creating sample users...')
        call_command('create_sample_users', '--count=10')

        # Populate marketplace with full data
        self.stdout.write('Populating marketplace...')
        call_command('populate_marketplace', '--users=40', '--journals=150')

        # Generate bestseller data
        self.stdout.write('Generating bestseller data...')
        call_command('generate_bestsellers', '--boost-sales')

        # Create featured content
        self.stdout.write('Creating featured content...')
        call_command('create_featured_content')

        # Simulate marketplace activity
        self.stdout.write('Simulating marketplace activity...')
        call_command('simulate_marketplace_activity', '--days=30')

        # Update statistics
        self.stdout.write('Updating final statistics...')
        call_command('update_marketplace_stats')

        self.stdout.write(
            self.style.SUCCESS(
                '\n✅ Full setup complete!\n'
                'Admin: admin / admin123\n'
                '150 journals with comprehensive data\n'
                '50 users with realistic activity\n'
                'Bestsellers, reviews, tips, and purchases generated!'
            )
        )

    def standard_setup(self):
        """Standard setup for most use cases"""
        self.stdout.write(self.style.SUCCESS('📚 Standard Marketplace Setup'))
        self.stdout.write('=' * 50)

        # Create admin user if doesn't exist
        if not User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Creating admin user...')
            User.objects.create_superuser(
                'admin', 'admin@example.com', 'admin123'
            )

        # Create sample users with diary entries
        self.stdout.write('Creating sample users...')
        call_command('create_sample_users', '--count=8')

        # Populate marketplace with moderate data
        self.stdout.write('Populating marketplace...')
        call_command('populate_marketplace', '--users=25', '--journals=75')

        # Generate some bestseller activity
        self.stdout.write('Generating marketplace activity...')
        call_command('generate_bestsellers')

        # Create featured content
        self.stdout.write('Creating featured content...')
        call_command('create_featured_content')

        # Simulate some marketplace activity
        self.stdout.write('Simulating recent activity...')
        call_command('simulate_marketplace_activity', '--days=14')

        # Update statistics
        self.stdout.write('Updating statistics...')
        call_command('update_marketplace_stats')

        self.stdout.write(
            self.style.SUCCESS(
                '\n✅ Standard setup complete!\n'
                'Admin: admin / admin123\n'
                '75 journals with realistic data\n'
                '33 users with diary entries and marketplace activity\n'
                'Categories, reviews, purchases, and tips created!'
            )
        )


# management/commands/demo_data.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from diary.models import Journal, JournalTag, JournalEntry, JournalLike, JournalReview, Tip
from decimal import Decimal
from django.utils import timezone
import random

class Command(BaseCommand):
    help = 'Create demo data for marketplace presentation'

    def handle(self, *args, **options):
        self.stdout.write('Creating demo data for marketplace...')

        # Create demo categories
        demo_categories = [
            ('travel', 'Travel & Adventure', 'blue'),
            ('mindfulness', 'Mindfulness & Wellness', 'green'),
            ('creativity', 'Creative Writing', 'purple'),
            ('personal-growth', 'Personal Growth', 'amber'),
            ('food', 'Food & Cooking', 'red'),
        ]

        for slug, name, color in demo_categories:
            JournalTag.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'color': color}
            )

        # Create demo users
        demo_users = [
            ('emily_travels', 'Emily', 'Davis', 'World traveler and storyteller'),
            ('mindful_marcus', 'Marcus', 'Chen', 'Meditation teacher'),
            ('creative_sarah', 'Sarah', 'Williams', 'Artist and writer'),
            ('growth_guru', 'Alex', 'Johnson', 'Life coach'),
            ('chef_maria', 'Maria', 'Rodriguez', 'Professional chef'),
        ]

        created_users = []
        for username, first, last, bio in demo_users:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': first,
                    'last_name': last,
                    'password': 'pbkdf2_sha256$600000$test$test'
                }
            )
            created_users.append(user)

        # Create demo journals
        demo_journals = [
            {
                'title': 'Wanderlust Chronicles: A Year in Southeast Asia',
                'author': 'emily_travels',
                'category': 'travel',
                'price': Decimal('8.99'),
                'description': 'A breathtaking journey through 7 countries with stunning photography and personal insights. Follow my adventures from bustling Bangkok to serene Bali beaches.',
                'entries': 45,
                'is_featured': True,
                'staff_pick': True
            },
            {
                'title': 'Mindfulness Journey: 365 Days of Peace',
                'author': 'mindful_marcus',
                'category': 'mindfulness',
                'price': Decimal('6.99'),
                'description': 'Daily meditations and mindfulness practices documented with personal reflections and growth insights. Transform your daily routine.',
                'entries': 365,
                'staff_pick': True
            },
            {
                'title': 'The Creative Spark: From Blank Page to Published',
                'author': 'creative_sarah',
                'category': 'creativity',
                'price': Decimal('12.99'),
                'description': 'My journey from aspiring writer to published author. Includes writing exercises, creative breakthroughs, and honest struggles.',
                'entries': 78,
                'staff_pick': True
            },
            {
                'title': 'Plant-Based Kitchen Adventures',
                'author': 'chef_maria',
                'category': 'food',
                'price': Decimal('0.00'),
                'description': 'Delicious plant-based recipes and cooking adventures. From family favorites to restaurant-quality dishes.',
                'entries': 52,
                'staff_pick': False
            },
            {
                'title': 'Building Confidence: My Personal Growth Story',
                'author': 'growth_guru',
                'category': 'personal-growth',
                'price': Decimal('15.99'),
                'description': 'An honest account of overcoming social anxiety and building unshakeable confidence. Practical strategies included.',
                'entries': 67,
                'staff_pick': False
            },
        ]

        created_journals = []
        for journal_data in demo_journals:
            author = User.objects.get(username=journal_data['author'])
            category = JournalTag.objects.get(slug=journal_data['category'])

            journal = Journal.objects.create(
                title=journal_data['title'],
                description=journal_data['description'],
                author=author,
                price=journal_data['price'],
                is_published=True,
                date_published=timezone.now() - timezone.timedelta(days=random.randint(1, 180)),
                is_staff_pick=journal_data['staff_pick'],
                featured=journal_data.get('is_featured', False),
                view_count=random.randint(500, 5000),
                total_tips=Decimal(str(random.randint(50, 1500)))
            )

            journal.marketplace_tags.add(category)

            # Create sample entries
            for i in range(journal_data['entries']):
                JournalEntry.objects.create(
                    journal=journal,
                    title=f"Entry {i+1}: Daily Reflection",
                    content=f"This is a sample entry content for journal '{journal.title}'. In a real scenario, this would contain meaningful, authentic content from the author's experiences.",
                    entry_date=(timezone.now() - timezone.timedelta(days=i)).date(),
                    is_included=True
                )

            created_journals.append(journal)

        # Create interactions
        all_users = list(User.objects.all())

        for journal in created_journals:
            # Create likes
            like_count = random.randint(10, 200)
            likers = random.sample([u for u in all_users if u != journal.author],
                                 min(like_count, len(all_users) - 1))
            for user in likers:
                JournalLike.objects.get_or_create(user=user, journal=journal)

            # Create reviews
            review_count = random.randint(5, 25)
            reviewers = random.sample([u for u in all_users if u != journal.author],
                                    min(review_count, len(all_users) - 1))

            review_templates = {
                5: ["Amazing journal! Life-changing insights.", "Absolutely loved every entry!", "Incredible storytelling and wisdom."],
                4: ["Really enjoyed this. Great perspectives.", "Well-written and inspiring.", "Definitely worth reading."],
                3: ["Good journal with some interesting parts.", "It was okay, had its moments.", "Decent read overall."],
                2: ["Not quite what I expected.", "Some good parts but overall disappointing.", "Struggled to connect with it."],
                1: ["Not for me.", "Didn't enjoy this one.", "Expected more."]
            }

            for user in reviewers:
                rating = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 20, 35, 30])[0]
                JournalReview.objects.create(
                    user=user,
                    journal=journal,
                    rating=rating,
                    review_text=random.choice(review_templates[rating])
                )

            # Create tips
            tip_count = random.randint(2, 15)
            tippers = random.sample([u for u in all_users if u != journal.author],
                                  min(tip_count, len(all_users) - 1))
            for user in tippers:
                amount = Decimal(str(random.choice([1.00, 2.00, 5.00, 10.00, 20.00])))
                Tip.objects.create(
                    journal=journal,
                    tipper=user,
                    recipient=journal.author,
                    amount=amount
                )

        # Update statistics
        for journal in created_journals:
            journal.update_cached_counts()
            journal.calculate_popularity()

        self.stdout.write(
            self.style.SUCCESS(
                f'Demo data created successfully!\n'
                f'Created {len(created_journals)} demo journals with:\n'
                f'- Realistic content and descriptions\n'
                f'- User interactions (likes, reviews, tips)\n'
                f'- Mixed free and premium pricing\n'
                f'- Staff picks and featured content\n'
                f'Ready for marketplace demonstration!'
            )
        )


# management/commands/reset_marketplace.py
from django.core.management.base import BaseCommand
from django.core.management import call_command
from diary.models import *

class Command(BaseCommand):
    help = 'Reset marketplace to clean state'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm you want to delete all marketplace data'
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    'This will delete ALL marketplace data!\n'
                    'Use --confirm to proceed.'
                )
            )
            return

        self.stdout.write('Resetting marketplace...')

        # Delete all marketplace data
        models_to_clear = [
            JournalReview, JournalPurchase, JournalLike, Tip,
            JournalEntry, Journal, JournalTag
        ]

        for model in models_to_clear:
            count = model.objects.count()
            model.objects.all().delete()
            self.stdout.write(f'Deleted {count} {model.__name__} records')

        self.stdout.write(
            self.style.SUCCESS(
                'Marketplace reset complete!\n'
                'Run python manage.py setup_marketplace to recreate data.'
            )
        )
