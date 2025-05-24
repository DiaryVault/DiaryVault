from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random
from faker import Faker

from diary.models import Entry, Tag, LifeChapter

class Command(BaseCommand):
    help = 'Create sample journal entries for existing users'

    def __init__(self):
        super().__init__()
        self.fake = Faker()

    def add_arguments(self, parser):
        parser.add_argument(
            '--entries-per-user',
            type=int,
            default=15,
            help='Number of entries to create per user (default: 15)'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Create entries for specific username only'
        )

    def handle(self, *args, **options):
        entries_per_user = options['entries_per_user']
        target_username = options.get('username')

        if target_username:
            users = User.objects.filter(username=target_username)
            if not users.exists():
                self.stdout.write(self.style.ERROR(f'User {target_username} not found'))
                return
        else:
            users = User.objects.all()

        self.stdout.write(f'Creating {entries_per_user} entries per user for {users.count()} users...')

        # Create common tags first
        self.create_common_tags()

        total_entries = 0
        for user in users:
            entries_created = self.create_entries_for_user(user, entries_per_user)
            total_entries += entries_created
            self.stdout.write(f'Created {entries_created} entries for {user.username}')

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {total_entries} total entries!')
        )

    def create_common_tags(self):
        """Create common tags that can be shared across entries"""
        common_tags = [
            'gratitude', 'reflection', 'goals', 'family', 'work', 'health',
            'travel', 'friends', 'growth', 'challenges', 'success', 'learning',
            'relationships', 'creativity', 'inspiration', 'mindfulness',
            'career', 'fitness', 'reading', 'music', 'nature', 'food',
            'photography', 'art', 'writing', 'meditation', 'exercise'
        ]

        for tag_name in common_tags:
            # Create tags without user association (they'll be created per user when needed)
            pass

    def create_entries_for_user(self, user, count):
        """Create diverse entries for a specific user"""

        # Create or get a life chapter for variety
        chapter = None if random.random() < 0.3 else self.get_or_create_chapter(user)

        entries_created = 0

        # Generate entries over the past year
        for i in range(count):
            # Random date within the past year
            days_ago = random.randint(1, 365)
            entry_date = timezone.now() - timedelta(days=days_ago)

            # Generate entry based on random themes
            entry_data = self.generate_entry_content()

            try:
                entry = Entry.objects.create(
                    user=user,
                    title=entry_data['title'],
                    content=entry_data['content'],
                    created_at=entry_date,
                    mood=entry_data['mood'],
                    chapter=chapter if random.random() < 0.7 else None  # 70% chance of being in chapter
                )

                # Add tags
                self.add_tags_to_entry(entry, entry_data['tags'])

                entries_created += 1

            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Error creating entry: {str(e)}'))
                continue

        return entries_created

    def get_or_create_chapter(self, user):
        """Get or create a life chapter for the user"""
        existing_chapters = LifeChapter.objects.filter(user=user)

        if existing_chapters.exists() and random.random() < 0.6:
            return random.choice(existing_chapters)

        # Create new chapter
        chapter_themes = [
            {'title': 'New Beginnings', 'desc': 'Starting fresh and embracing change', 'color': 'emerald'},
            {'title': 'Growth Phase', 'desc': 'Learning and developing personally', 'color': 'blue'},
            {'title': 'Career Focus', 'desc': 'Professional development and work life', 'color': 'purple'},
            {'title': 'Relationships', 'desc': 'Love, family, and friendships', 'color': 'pink'},
            {'title': 'Health Journey', 'desc': 'Physical and mental wellness', 'color': 'green'},
            {'title': 'Creative Expression', 'desc': 'Artistic and creative pursuits', 'color': 'orange'},
        ]

        theme = random.choice(chapter_themes)

        chapter = LifeChapter.objects.create(
            user=user,
            title=theme['title'],
            description=theme['desc'],
            color=theme['color'],
            start_date=timezone.now().date() - timedelta(days=random.randint(30, 200)),
            is_active=random.random() < 0.3  # 30% chance of being active
        )

        return chapter

    def generate_entry_content(self):
        """Generate realistic journal entry content"""

        entry_templates = [
            {
                'title': 'Morning Reflections',
                'content': "Started the day with some quiet time to think about what's ahead. There's something peaceful about the early morning hours when the world is still waking up. I've been trying to be more intentional about how I spend these moments.\n\nToday feels different somehow - maybe it's the changing season or just my mindset shifting. I'm grateful for the small routines that ground me and give structure to my days.\n\nThinking about my goals and what I want to accomplish, not just today but in the bigger picture. It's easy to get caught up in the day-to-day tasks and forget about the larger vision.",
                'mood': 'peaceful',
                'tags': ['reflection', 'morning', 'goals', 'gratitude']
            },
            {
                'title': 'Challenging Day at Work',
                'content': "Work was particularly intense today. Had that meeting I'd been dreading, and while it didn't go exactly as planned, I'm proud of how I handled myself. There were moments when I felt overwhelmed, but I managed to stay focused and contribute meaningfully.\n\nI'm learning that professional growth often comes through these uncomfortable situations. Each challenge is teaching me something about my capabilities and areas where I need to improve.\n\nComing home tonight, I felt drained but accomplished. Sometimes the hardest days teach us the most about ourselves.",
                'mood': 'determined',
                'tags': ['work', 'challenges', 'growth', 'career']
            },
            {
                'title': 'Time with Family',
                'content': "Spent the afternoon with family today, and it reminded me how important these connections are. We don't get together as often as we should, but when we do, it feels like no time has passed at all.\n\nThere's something special about the people who knew you before you became who you are now. They see all the versions of you and love you anyway. Today was filled with laughter, stories, and that comfortable feeling of being completely yourself.\n\nI want to be more intentional about nurturing these relationships. Life gets busy, but family is what matters most.",
                'mood': 'content',
                'tags': ['family', 'relationships', 'love', 'gratitude']
            },
            {
                'title': 'Personal Breakthrough',
                'content': "Had a moment of clarity today that felt significant. I've been struggling with [situation] for weeks, and suddenly the path forward became clear. It's amazing how solutions can appear when you least expect them.\n\nThis experience reminded me that sometimes we need to stop forcing outcomes and trust the process. The answer was there all along; I just needed to be in the right headspace to see it.\n\nI'm excited about what this means for the future and grateful for the journey that led me here, even the difficult parts.",
                'mood': 'inspired',
                'tags': ['breakthrough', 'growth', 'inspiration', 'clarity']
            },
            {
                'title': 'Quiet Evening',
                'content': "Sometimes the best evenings are the quiet ones. No big plans, no social obligations, just time to be present with myself and my thoughts. I made a simple dinner, read for a while, and let my mind wander.\n\nIn our busy world, these moments of stillness feel like a luxury. But I'm realizing they're actually a necessity. This is when ideas surface, when emotions process, when healing happens.\n\nTonight I'm grateful for the peace that comes with solitude and the reminder that I enjoy my own company.",
                'mood': 'peaceful',
                'tags': ['solitude', 'peace', 'reading', 'mindfulness']
            },
            {
                'title': 'New Experience',
                'content': "Tried something completely new today, and it was both terrifying and exhilarating. I've been in my comfort zone for too long, and this felt like a necessary push into unfamiliar territory.\n\nThe experience didn't go perfectly - there were awkward moments and things I'd do differently next time. But that's exactly the point. Growth happens in the space between comfort and panic, and today I lived in that space.\n\nI'm proud of myself for taking the risk and excited about what other new experiences might be waiting for me.",
                'mood': 'excited',
                'tags': ['new experiences', 'growth', 'courage', 'adventure']
            },
            {
                'title': 'Friendship Appreciation',
                'content': "Had a long conversation with a close friend today, the kind where you lose track of time and cover everything from daily life to deep philosophical questions. These friendships are such a gift.\n\nWhat I value most about our friendship is the honesty. We can share our struggles, celebrate our wins, and challenge each other to be better. There's no judgment, just acceptance and genuine care.\n\nI'm reminded today how important it is to invest in relationships that feed your soul. Good friends are rare treasures.",
                'mood': 'grateful',
                'tags': ['friendship', 'relationships', 'gratitude', 'connection']
            },
            {
                'title': 'Creative Flow',
                'content': "Had one of those rare creative sessions today where everything just flowed. Hours passed without me noticing, and I was completely absorbed in the process. These moments remind me why I love creative work.\n\nThere's something magical about the creative process when it's working. Ideas build on each other, problems solve themselves, and you feel connected to something larger than yourself.\n\nI want to create more space for these experiences in my life. They're not just productive; they're nourishing for the soul.",
                'mood': 'creative',
                'tags': ['creativity', 'flow', 'art', 'inspiration']
            },
            {
                'title': 'Health and Wellness',
                'content': "Made some positive choices for my health today, and I can already feel the difference. It's amazing how much our physical state affects our mental and emotional well-being.\n\nI've been more consistent with exercise and mindful eating lately, and the cumulative effect is noticeable. More energy, better mood, clearer thinking. It reinforces that taking care of myself isn't selfish - it's necessary.\n\nSmall daily choices add up to significant changes over time. Today was another step in the right direction.",
                'mood': 'energetic',
                'tags': ['health', 'fitness', 'wellness', 'self-care']
            },
            {
                'title': 'Learning and Growth',
                'content': "Learned something new today that challenged my previous assumptions. It's humbling and exciting to realize how much there is still to discover and understand.\n\nI've been thinking about the importance of staying curious and open to new information. It's easy to get set in our ways, but growth requires flexibility and willingness to change our minds.\n\nEvery day is an opportunity to learn something new, whether from books, experiences, or other people. Today was a good reminder of that.",
                'mood': 'curious',
                'tags': ['learning', 'growth', 'curiosity', 'education']
            }
        ]

        # Select random template and customize it
        template = random.choice(entry_templates)

        # Sometimes modify the content slightly for variety
        content = template['content']
        if '[situation]' in content:
            situations = ['a work project', 'a relationship issue', 'a personal goal', 'a difficult decision', 'a creative block']
            content = content.replace('[situation]', random.choice(situations))

        return {
            'title': template['title'],
            'content': content,
            'mood': template['mood'],
            'tags': template['tags']
        }

    def add_tags_to_entry(self, entry, tag_names):
        """Add tags to an entry"""
        for tag_name in tag_names:
            # Get or create tag for this user
            tag, created = Tag.objects.get_or_create(
                name=tag_name,
                user=entry.user
            )
            entry.tags.add(tag)
