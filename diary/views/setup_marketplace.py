from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from diary.models import Journal, JournalEntry, JournalTag
from decimal import Decimal
import random

class Command(BaseCommand):
    help = 'Set up sample marketplace data'

    def handle(self, *args, **options):
        # Create sample tags
        tags_data = [
            ('travel', 'Travel & Adventure'),
            ('personal-growth', 'Personal Growth'),
            ('relationships', 'Relationships'),
            ('career', 'Career & Work'),
            ('health', 'Health & Wellness'),
            ('creativity', 'Art & Creativity'),
            ('family', 'Family Life'),
            ('spirituality', 'Spirituality'),
        ]

        for slug, name in tags_data:
            tag, created = JournalTag.objects.get_or_create(
                slug=slug,
                defaults={'name': name}
            )
            if created:
                self.stdout.write(f'Created tag: {name}')

        # Create sample journals (if users exist)
        users = User.objects.all()[:5]  # Use first 5 users

        for user in users:
            # Create a sample journal
            journal = Journal.objects.create(
                title=f"Life Reflections by {user.username}",
                description="A collection of personal thoughts and experiences",
                author=user,
                price=Decimal(str(random.uniform(2.99, 19.99))),
                is_published=True,
                view_count=random.randint(50, 500)
            )

            # Add sample entries
            for i in range(5):
                JournalEntry.objects.create(
                    journal=journal,
                    title=f"Chapter {i+1}: Personal Growth",
                    content=f"This is a sample entry about personal growth and life experiences. Entry {i+1} contains meaningful reflections...",
                    is_included=True
                )

            journal.update_cached_counts()
            self.stdout.write(f'Created journal for {user.username}')

        self.stdout.write(
            self.style.SUCCESS('Successfully set up marketplace data!')
        )
