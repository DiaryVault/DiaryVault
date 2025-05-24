# diary/management/commands/create_realistic_marketplace.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.base import ContentFile
from datetime import datetime, timedelta
import random
import requests
from PIL import Image, ImageDraw, ImageFont
import io
import os

from diary.models import (
    Entry, Tag, LifeChapter, Journal, JournalEntry, JournalTag,
    UserPreference, Biography
)

class Command(BaseCommand):
    help = 'Create realistic marketplace data with actual images and content'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=3,
            help='Number of sample users to create'
        )
        parser.add_argument(
            '--journals-per-user',
            type=int,
            default=2,
            help='Number of journals per user'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing sample data first'
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing sample data...')
            User.objects.filter(username__startswith='author_').delete()
            Journal.objects.filter(title__contains='Sample').delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing sample data'))

        users_count = options['users']
        journals_per_user = options['journals_per_user']

        self.stdout.write(f'Creating {users_count} authors with {journals_per_user} journals each...')

        # Create realistic author profiles
        authors_data = [
            {
                'username': 'author_sarah_travels',
                'first_name': 'Sarah',
                'last_name': 'Mitchell',
                'email': 'sarah@example.com',
                'bio': 'Travel enthusiast and digital nomad sharing stories from around the world.',
                'specialty': 'travel'
            },
            {
                'username': 'author_mike_entrepreneur',
                'first_name': 'Michael',
                'last_name': 'Chen',
                'email': 'mike@example.com',
                'bio': 'Startup founder documenting the entrepreneurial journey.',
                'specialty': 'business'
            },
            {
                'username': 'author_emma_wellness',
                'first_name': 'Emma',
                'last_name': 'Rodriguez',
                'email': 'emma@example.com',
                'bio': 'Wellness coach and mindfulness practitioner sharing daily reflections.',
                'specialty': 'wellness'
            },
            {
                'username': 'author_david_student',
                'first_name': 'David',
                'last_name': 'Thompson',
                'email': 'david@example.com',
                'bio': 'Graduate student exploring philosophy and personal growth.',
                'specialty': 'academic'
            },
            {
                'username': 'author_lisa_parent',
                'first_name': 'Lisa',
                'last_name': 'Johnson',
                'email': 'lisa@example.com',
                'bio': 'Working mom sharing the beautiful chaos of family life.',
                'specialty': 'family'
            }
        ]

        created_authors = []
        for i in range(min(users_count, len(authors_data))):
            author_data = authors_data[i]
            author = self.create_realistic_author(author_data)
            created_authors.append(author)
            self.create_realistic_journals(author, author_data['specialty'], journals_per_user)

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {len(created_authors)} authors with realistic journals!')
        )

    def create_realistic_author(self, author_data):
        """Create a realistic author with detailed profile"""
        username = author_data['username']

        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Author {username} already exists, skipping...')
            return User.objects.get(username=username)

        user = User.objects.create_user(
            username=username,
            email=author_data['email'],
            password='authorpass123',
            first_name=author_data['first_name'],
            last_name=author_data['last_name']
        )

        # Create user preferences
        try:
            UserPreference.objects.create(
                user=user,
                writing_style=random.choice(['reflective', 'analytical', 'creative', 'narrative']),
                tone=random.choice(['positive', 'balanced', 'thoughtful', 'inspiring']),
                focus_areas=f"{author_data['specialty']}, personal growth, storytelling",
                include_questions=True
            )
        except Exception as e:
            self.stdout.write(f'Could not create preferences: {e}')

        self.stdout.write(f'Created author: {user.first_name} {user.last_name} (@{username})')
        return user

    def create_realistic_journals(self, author, specialty, count):
        """Create realistic journals with actual content and images"""

        # Journal templates based on specialty
        journal_templates = {
            'travel': [
                {
                    'title': 'Wanderlust Chronicles: A Year of Solo Travel',
                    'description': 'Join me on an incredible journey across 15 countries as I document the highs, lows, and unexpected discoveries of solo travel. From getting lost in Tokyo\'s backstreets to watching sunrises over Machu Picchu.',
                    'price': 12.99,
                    'cover_theme': 'travel',
                    'tags': ['Travel', 'Solo Travel', 'Adventure'],
                    'entries': [
                        {
                            'title': 'Lost in Translation - Tokyo Day 1',
                            'content': 'Arrived in Tokyo completely jet-lagged and overwhelmed. The neon signs, the crowds, the language barrier - everything felt surreal. Spent my first day wandering Shibuya, getting lost more times than I can count. But there\'s something magical about being completely out of your comfort zone. Had my first authentic ramen at a tiny shop where the chef didn\'t speak English, but his smile said everything. Sometimes the best adventures start with being completely lost.'
                        },
                        {
                            'title': 'Sunrise at Machu Picchu',
                            'content': 'Woke up at 4 AM for the trek to watch sunrise over Machu Picchu. The altitude made every step a challenge, but as the sun crested over the ancient ruins, I understood why this moment is on every traveler\'s bucket list. Standing there, surrounded by clouds and history, I felt incredibly small yet profoundly connected to something larger than myself. This is why I travel - for moments that photos can never capture.'
                        },
                        {
                            'title': 'The Kindness of Strangers in Morocco',
                            'content': 'Got completely turned around in the medina of Marrakech today. Just when panic was setting in, a local shopkeeper named Hassan noticed my confusion. He not only gave me directions but invited me for mint tea and spent an hour telling me stories about his family\'s rug-making tradition spanning five generations. Reminded me that the world is full of good people, and sometimes getting lost leads you exactly where you need to be.'
                        }
                    ]
                },
                {
                    'title': 'Digital Nomad Diaries: Working from Paradise',
                    'description': 'The reality behind the Instagram posts - what it\'s really like to work remotely while traveling. From WiFi disasters in Bali to finding community in co-working spaces across the globe.',
                    'price': 8.99,
                    'cover_theme': 'nomad',
                    'tags': ['Digital Nomad', 'Remote Work', 'Travel'],
                    'entries': [
                        {
                            'title': 'The Great WiFi Disaster of Canggu',
                            'content': 'Important client call at 9 AM. WiFi dies at 8:55 AM. This is the unglamorous side of digital nomad life that Instagram doesn\'t show. Frantically running through Canggu trying to find stable internet, laptop in hand, looking like a complete tourist. Finally found refuge in a local warung where the owner let me use their connection. Lesson learned: always have three backup plans for internet.'
                        }
                    ]
                }
            ],
            'business': [
                {
                    'title': 'Startup Rollercoaster: From Idea to Exit',
                    'description': 'The unfiltered truth about building a startup from scratch. Follow my journey through funding rounds, product pivots, team building, and the emotional rollercoaster of entrepreneurship.',
                    'price': 15.99,
                    'cover_theme': 'business',
                    'tags': ['Entrepreneurship', 'Startup', 'Business'],
                    'entries': [
                        {
                            'title': 'The Day We Almost Ran Out of Money',
                            'content': 'Checked our bank account this morning: $2,847 left. Payroll is due Friday. This is the moment every founder dreads but rarely talks about. The weight of responsibility for my team\'s livelihoods keeps me up at night. But it\'s also incredibly clarifying - when your back is against the wall, you find solutions you never knew existed. Made 47 calls today. Three promising leads. Sometimes survival breeds innovation.'
                        },
                        {
                            'title': 'Our First Customer Success Story',
                            'content': 'Sarah from Portland just sent us a message that made my entire year. Our app helped her small bakery increase online orders by 300% during the pandemic. She said we literally saved her business. This is why we do what we do. Not for the funding rounds or the tech blogs - for real people solving real problems. Printed her message and put it on our wall. On the hard days, I\'ll remember Sarah.'
                        }
                    ]
                }
            ],
            'wellness': [
                {
                    'title': 'Mindful Mornings: A Year of Daily Meditation',
                    'description': 'Documenting my journey from complete meditation skeptic to daily practitioner. Raw, honest reflections on building mindfulness habits and finding peace in chaos.',
                    'price': 9.99,
                    'cover_theme': 'wellness',
                    'tags': ['Mindfulness', 'Meditation', 'Self-Care'],
                    'entries': [
                        {
                            'title': 'Day 1: This is Harder Than It Looks',
                            'content': 'Committed to meditating for 10 minutes every morning. Made it exactly 3 minutes before my mind started planning my entire day. Who knew sitting still could be so difficult? My thoughts were like a browser with 47 tabs open. But I stayed with it, even when every instinct said to quit. Small victories count, right?'
                        },
                        {
                            'title': 'Day 100: Finding Stillness in the Storm',
                            'content': 'Woke up to my phone buzzing with work crisis texts. Old me would have immediately jumped into reactive mode. Instead, I sat for my usual 20 minutes of meditation first. The crisis didn\'t get worse in those 20 minutes, but my capacity to handle it got significantly better. This practice is changing me in ways I never expected.'
                        }
                    ]
                }
            ],
            'academic': [
                {
                    'title': 'Graduate School Chronicles: Philosophy and Life',
                    'description': 'Navigating the world of academia while trying to make sense of life\'s big questions. A graduate student\'s perspective on learning, research, and personal growth.',
                    'price': 7.99,
                    'cover_theme': 'academic',
                    'tags': ['Academic Life', 'Philosophy', 'Graduate School'],
                    'entries': [
                        {
                            'title': 'Imposter Syndrome in Seminar Room 304',
                            'content': 'Sat in advanced epistemology seminar today feeling like a complete fraud. Everyone else seemed to effortlessly reference obscure philosophers while I struggled to keep up with the basic concepts. Professor asked my thoughts on Gettier problems and I froze. But walking home, I realized that feeling lost is part of learning. Socrates said the wise person knows they know nothing. Maybe I\'m wiser than I thought.'
                        }
                    ]
                }
            ],
            'family': [
                {
                    'title': 'Motherhood Unfiltered: The Beautiful Chaos',
                    'description': 'Real stories from the trenches of parenting. No Pinterest-perfect moments here - just honest reflections on raising kids while trying to maintain sanity.',
                    'price': 6.99,
                    'cover_theme': 'family',
                    'tags': ['Parenting', 'Family Life', 'Motherhood'],
                    'entries': [
                        {
                            'title': 'The Great Goldfish Incident of Tuesday',
                            'content': 'Emma\'s goldfish died today. What started as a simple explanation about pets going to "fish heaven" turned into a 2-hour philosophical discussion about life, death, and whether goldfish have souls. Kids have this amazing ability to ask the questions that really matter. We had a proper funeral in the backyard. Emma insisted on singing "Amazing Grace." Sometimes parenting is about learning alongside them.'
                        }
                    ]
                }
            ]
        }

        # Get templates for this specialty
        templates = journal_templates.get(specialty, journal_templates['travel'])

        for i in range(min(count, len(templates))):
            template = templates[i]
            journal = self.create_journal_with_content(author, template)
            self.stdout.write(f'Created journal: {journal.title}')

    def create_journal_with_content(self, author, template):
        """Create a journal with realistic content and cover image"""

        # Create the journal
        journal = Journal.objects.create(
            title=template['title'],
            description=template['description'],
            author=author,
            is_published=True,
            privacy_setting='public'
        )

        # Set price if field exists
        if hasattr(journal, 'price'):
            journal.price = template['price']

        # Set publication date
        if hasattr(journal, 'date_published'):
            journal.date_published = timezone.now() - timedelta(days=random.randint(1, 90))

        # Set view count and other stats
        if hasattr(journal, 'view_count'):
            journal.view_count = random.randint(50, 2000)

        if hasattr(journal, 'total_tips'):
            journal.total_tips = random.randint(0, 150)

        # Create and attach cover image
        cover_image = self.generate_cover_image(template['title'], template['cover_theme'])
        if cover_image:
            journal.cover_image.save(
                f'journal_cover_{journal.id}.png',
                cover_image,
                save=True
            )

        journal.save()

        # Add tags
        if hasattr(journal, 'marketplace_tags'):
            for tag_name in template['tags']:
                tag, created = JournalTag.objects.get_or_create(
                    name=tag_name,
                    defaults={
                        'slug': tag_name.lower().replace(' ', '-'),
                        'description': f'Journals about {tag_name.lower()}',
                        'color': random.choice(['blue', 'green', 'purple', 'amber', 'red'])
                    }
                )
                journal.marketplace_tags.add(tag)

        # Create journal entries
        for entry_data in template['entries']:
            try:
                JournalEntry.objects.create(
                    journal=journal,
                    title=entry_data['title'],
                    content=entry_data['content'],
                    entry_date=(timezone.now() - timedelta(days=random.randint(30, 365))).date(),
                    is_included=True
                )
            except Exception as e:
                self.stdout.write(f'Could not create journal entry: {e}')

        # Add some likes
        if hasattr(journal, 'likes'):
            # Get other sample users to like this journal
            other_users = User.objects.exclude(id=author.id)[:random.randint(5, 20)]
            for user in other_users:
                journal.likes.add(user)

        return journal

    def generate_cover_image(self, title, theme):
        """Generate a beautiful cover image for the journal"""
        try:
            # Create a 400x600 image (book-like proportions)
            width, height = 400, 600
            image = Image.new('RGB', (width, height))
            draw = ImageDraw.Draw(image)

            # Theme-based color schemes
            color_schemes = {
                'travel': {
                    'bg': [(135, 206, 235), (70, 130, 180)],  # Sky blue gradient
                    'accent': (255, 215, 0),  # Gold
                    'text': (255, 255, 255)   # White
                },
                'business': {
                    'bg': [(75, 0, 130), (138, 43, 226)],     # Purple gradient
                    'accent': (255, 165, 0),  # Orange
                    'text': (255, 255, 255)   # White
                },
                'wellness': {
                    'bg': [(144, 238, 144), (60, 179, 113)],  # Green gradient
                    'accent': (255, 192, 203), # Pink
                    'text': (255, 255, 255)    # White
                },
                'academic': {
                    'bg': [(105, 105, 105), (169, 169, 169)], # Gray gradient
                    'accent': (255, 140, 0),   # Dark orange
                    'text': (255, 255, 255)    # White
                },
                'family': {
                    'bg': [(255, 182, 193), (255, 160, 122)], # Pink gradient
                    'accent': (255, 215, 0),   # Gold
                    'text': (255, 255, 255)    # White
                },
                'nomad': {
                    'bg': [(255, 99, 71), (255, 165, 0)],     # Orange gradient
                    'accent': (255, 255, 255), # White
                    'text': (255, 255, 255)    # White
                }
            }

            scheme = color_schemes.get(theme, color_schemes['travel'])

            # Create gradient background
            for y in range(height):
                ratio = y / height
                r = int(scheme['bg'][0][0] * (1 - ratio) + scheme['bg'][1][0] * ratio)
                g = int(scheme['bg'][0][1] * (1 - ratio) + scheme['bg'][1][1] * ratio)
                b = int(scheme['bg'][0][2] * (1 - ratio) + scheme['bg'][1][2] * ratio)
                draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))

            # Add decorative elements
            self.add_decorative_elements(draw, width, height, scheme, theme)

            # Add title text
            self.add_title_text(draw, title, width, height, scheme)

            # Convert to ContentFile
            img_io = io.BytesIO()
            image.save(img_io, format='PNG', quality=95)
            img_io.seek(0)

            return ContentFile(img_io.getvalue())

        except Exception as e:
            self.stdout.write(f'Could not generate cover image: {e}')
            return None

    def add_decorative_elements(self, draw, width, height, scheme, theme):
        """Add theme-specific decorative elements"""
        accent_color = scheme['accent']

        if theme == 'travel':
            # Add mountain silhouettes
            points = [(0, height//2), (width//4, height//3), (width//2, height//2.5),
                     (3*width//4, height//2.8), (width, height//2.2), (width, height), (0, height)]
            draw.polygon(points, fill=(0, 0, 0, 100))

        elif theme == 'business':
            # Add geometric patterns
            for i in range(5):
                x = width - 60 + i * 10
                draw.rectangle([(x, 50), (x + 5, 150 - i * 20)], fill=accent_color)

        elif theme == 'wellness':
            # Add circular zen patterns
            for i in range(3):
                radius = 30 + i * 15
                draw.ellipse([(width - 100 - radius, 80 - radius),
                             (width - 100 + radius, 80 + radius)],
                           outline=accent_color, width=2)

        elif theme == 'family':
            # Add heart shapes (simplified as circles)
            for i in range(4):
                x = width - 80 + (i % 2) * 20
                y = height - 150 + (i // 2) * 25
                draw.ellipse([(x, y), (x + 15, y + 12)], fill=accent_color)

    def add_title_text(self, draw, title, width, height, scheme):
        """Add title text to the cover"""
        try:
            # Try to use a nice font, fall back to default if not available
            try:
                font_large = ImageFont.truetype("arial.ttf", 32)
                font_small = ImageFont.truetype("arial.ttf", 18)
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

            # Split title into lines for better formatting
            words = title.split()
            lines = []
            current_line = []

            for word in words:
                test_line = ' '.join(current_line + [word])
                # Rough estimate of text width
                if len(test_line) * 12 < width - 40:  # 40px margin
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                        current_line = [word]
                    else:
                        lines.append(word)

            if current_line:
                lines.append(' '.join(current_line))

            # Draw title
            y_offset = height // 2 - (len(lines) * 40) // 2
            for i, line in enumerate(lines):
                # Get text size for centering
                bbox = draw.textbbox((0, 0), line, font=font_large)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                y = y_offset + i * 45

                # Add text shadow
                draw.text((x + 2, y + 2), line, fill=(0, 0, 0, 128), font=font_large)
                # Add main text
                draw.text((x, y), line, fill=scheme['text'], font=font_large)

        except Exception as e:
            # Fallback: simple text
            draw.text((20, height // 2), title[:30], fill=scheme['text'])

class JournalTagCommand(BaseCommand):
    help = 'Create comprehensive journal tags'

    def handle(self, *args, **options):
        tags_data = [
            {'name': 'Personal Growth', 'color': 'emerald', 'description': 'Journals focused on self-improvement and personal development'},
            {'name': 'Travel Adventures', 'color': 'blue', 'description': 'Stories from around the world and travel experiences'},
            {'name': 'Entrepreneurship', 'color': 'purple', 'description': 'Business building, startup stories, and entrepreneurial journeys'},
            {'name': 'Mindfulness', 'color': 'green', 'description': 'Meditation, mindfulness practices, and mental wellness'},
            {'name': 'Family Life', 'color': 'pink', 'description': 'Parenting, family relationships, and domestic life'},
            {'name': 'Academic Journey', 'color': 'gray', 'description': 'Student life, research, and academic experiences'},
            {'name': 'Creative Writing', 'color': 'amber', 'description': 'Fiction, poetry, and creative expression'},
            {'name': 'Daily Reflections', 'color': 'indigo', 'description': 'Everyday thoughts and daily life observations'},
            {'name': 'Wellness Journey', 'color': 'teal', 'description': 'Health, fitness, and overall well-being'},
            {'name': 'Career Development', 'color': 'red', 'description': 'Professional growth and career transitions'}
        ]

        for tag_data in tags_data:
            tag, created = JournalTag.objects.get_or_create(
                name=tag_data['name'],
                defaults={
                    'slug': tag_data['name'].lower().replace(' ', '-'),
                    'description': tag_data['description'],
                    'color': tag_data['color']
                }
            )
            if created:
                self.stdout.write(f'Created tag: {tag.name}')

        self.stdout.write(self.style.SUCCESS(f'Successfully created/updated journal tags!'))
