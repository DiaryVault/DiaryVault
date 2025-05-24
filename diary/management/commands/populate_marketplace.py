from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta, date
import random
from faker import Faker

from diary.models import Entry, Journal, JournalEntry, JournalTag, JournalLike, Tip

class Command(BaseCommand):
    help = 'Create a rich marketplace with diverse journals and content'

    def __init__(self):
        super().__init__()
        self.fake = Faker()

    def add_arguments(self, parser):
        parser.add_argument(
            '--journals',
            type=int,
            default=50,
            help='Number of journals to create (default: 50)'
        )
        parser.add_argument(
            '--users',
            type=int,
            default=25,
            help='Number of sample users to create (default: 25)'
        )

    def handle(self, *args, **options):
        num_journals = options['journals']
        num_users = options['users']

        self.stdout.write(f'Creating marketplace with {num_journals} journals and {num_users} users...')

        # Create sample users first
        users = self.create_sample_users(num_users)

        # Create comprehensive journal tags
        tags = self.create_journal_tags()

        # Create diverse journals
        journals = self.create_diverse_journals(users, tags, num_journals)

        # Add engagement (likes, tips, views)
        self.add_engagement(journals, users)

        # Create featured content
        self.mark_featured_content(journals)

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created marketplace with {len(journals)} journals!')
        )

    def create_sample_users(self, num_users):
        """Create diverse sample users with realistic profiles"""
        self.stdout.write('Creating sample users...')

        users = []

        # Predefined user personas for variety
        personas = [
            {'first': 'Sarah', 'last': 'Johnson', 'profession': 'writer', 'age': 28},
            {'first': 'Michael', 'last': 'Chen', 'profession': 'developer', 'age': 32},
            {'first': 'Emma', 'last': 'Rodriguez', 'profession': 'teacher', 'age': 26},
            {'first': 'David', 'last': 'Thompson', 'profession': 'entrepreneur', 'age': 35},
            {'first': 'Lisa', 'last': 'Williams', 'profession': 'artist', 'age': 29},
            {'first': 'James', 'last': 'Brown', 'profession': 'consultant', 'age': 31},
            {'first': 'Maria', 'last': 'Garcia', 'profession': 'nurse', 'age': 27},
            {'first': 'Ryan', 'last': 'Miller', 'profession': 'photographer', 'age': 33},
            {'first': 'Amy', 'last': 'Davis', 'profession': 'designer', 'age': 25},
            {'first': 'Kevin', 'last': 'Wilson', 'profession': 'coach', 'age': 38},
        ]

        for i in range(num_users):
            if i < len(personas):
                persona = personas[i]
                username = f"{persona['first'].lower()}.{persona['last'].lower()}"
                first_name = persona['first']
                last_name = persona['last']
            else:
                username = self.fake.user_name()
                first_name = self.fake.first_name()
                last_name = self.fake.last_name()

            # Create user if doesn't exist
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': self.fake.email(),
                    'date_joined': timezone.now() - timedelta(days=random.randint(30, 365))
                }
            )

            if created:
                users.append(user)
                self.stdout.write(f'Created user: {user.username}')
            else:
                users.append(user)

        return users

    def create_journal_tags(self):
        """Create comprehensive journal categories"""
        self.stdout.write('Creating journal tags...')

        tag_data = [
            {'name': 'Personal Growth', 'color': 'emerald', 'desc': 'Self-improvement and development journeys'},
            {'name': 'Mental Health', 'color': 'blue', 'desc': 'Mental wellness and mindfulness practices'},
            {'name': 'Travel Adventures', 'color': 'orange', 'desc': 'Travel experiences and cultural discoveries'},
            {'name': 'Career Journey', 'color': 'purple', 'desc': 'Professional development and work experiences'},
            {'name': 'Relationships', 'color': 'pink', 'desc': 'Love, friendship, and family relationships'},
            {'name': 'Parenting', 'color': 'yellow', 'desc': 'Motherhood, fatherhood, and family life'},
            {'name': 'Health & Fitness', 'color': 'green', 'desc': 'Physical health, fitness, and wellness journeys'},
            {'name': 'Creativity', 'color': 'indigo', 'desc': 'Artistic pursuits and creative expression'},
            {'name': 'Spirituality', 'color': 'teal', 'desc': 'Spiritual growth and mindfulness practices'},
            {'name': 'Entrepreneurship', 'color': 'red', 'desc': 'Business building and startup experiences'},
            {'name': 'Student Life', 'color': 'amber', 'desc': 'Academic experiences and learning journeys'},
            {'name': 'Recovery', 'color': 'cyan', 'desc': 'Healing and recovery experiences'},
            {'name': 'Adventure', 'color': 'lime', 'desc': 'Outdoor adventures and exciting experiences'},
            {'name': 'Daily Reflections', 'color': 'gray', 'desc': 'Everyday thoughts and observations'},
            {'name': 'Life Transitions', 'color': 'violet', 'desc': 'Major life changes and transitions'},
        ]

        tags = []
        for tag_info in tag_data:
            tag, created = JournalTag.objects.get_or_create(
                name=tag_info['name'],
                defaults={
                    'slug': tag_info['name'].lower().replace(' ', '-').replace('&', 'and'),
                    'description': tag_info['desc'],
                    'color': tag_info['color']
                }
            )
            tags.append(tag)
            if created:
                self.stdout.write(f'Created tag: {tag.name}')

        return tags

    def create_diverse_journals(self, users, tags, num_journals):
        """Create diverse, engaging journals"""
        self.stdout.write(f'Creating {num_journals} diverse journals...')

        # Journal templates with realistic content
        journal_templates = [
            {
                'title_templates': [
                    "My Journey to {goal}",
                    "Finding {value} in {context}",
                    "Life After {transition}",
                    "The Road to {destination}",
                    "{year} Reflections"
                ],
                'categories': ['Personal Growth', 'Daily Reflections'],
                'price_range': (0, 15.99),
                'entry_count': (5, 15)
            },
            {
                'title_templates': [
                    "Backpacking Through {location}",
                    "Living in {country}: A {duration} Experience",
                    "Solo Travel Diaries: {experience}",
                    "Cultural Discoveries in {region}"
                ],
                'categories': ['Travel Adventures', 'Adventure'],
                'price_range': (7.99, 24.99),
                'entry_count': (8, 20)
            },
            {
                'title_templates': [
                    "First-Time {parent_type} Chronicles",
                    "Raising {child_age} in {era}",
                    "The Joys and Challenges of {family_situation}",
                    "Bedtime Stories and Beyond"
                ],
                'categories': ['Parenting', 'Relationships'],
                'price_range': (0, 12.99),
                'entry_count': (10, 25)
            },
            {
                'title_templates': [
                    "From Idea to Reality: Building {business}",
                    "Startup Life: {stage} Stage Chronicles",
                    "Entrepreneur's Diary: {journey_type}",
                    "Building {company} from Scratch"
                ],
                'categories': ['Entrepreneurship', 'Career Journey'],
                'price_range': (12.99, 29.99),
                'entry_count': (6, 18)
            },
            {
                'title_templates': [
                    "Healing Heart: {recovery_type} Journey",
                    "Finding Light in {challenge}",
                    "Recovery Diaries: {process}",
                    "Overcoming {obstacle}: A Personal Story"
                ],
                'categories': ['Recovery', 'Mental Health'],
                'price_range': (0, 9.99),
                'entry_count': (12, 30)
            },
            {
                'title_templates': [
                    "Creative Awakening: {art_form} Journey",
                    "From Blank Canvas to {creation}",
                    "Artist's Soul: {creative_process}",
                    "Finding My Voice Through {medium}"
                ],
                'categories': ['Creativity', 'Personal Growth'],
                'price_range': (5.99, 19.99),
                'entry_count': (7, 16)
            }
        ]

        journals = []

        for i in range(num_journals):
            # Select random user and template
            user = random.choice(users)
            template = random.choice(journal_templates)

            # Generate journal details
            title = self.generate_journal_title(template['title_templates'])
            description = self.generate_journal_description(title, template['categories'])
            price = round(random.uniform(*template['price_range']), 2)

            # Randomly make some journals free
            if random.random() < 0.3:  # 30% chance of being free
                price = 0.00

            # Create journal
            journal = Journal.objects.create(
                title=title,
                description=description,
                author=user,
                is_published=True,
                privacy_setting='public',
                price=price,
                date_published=timezone.now() - timedelta(days=random.randint(1, 90)),
                view_count=random.randint(5, 1000),
                total_tips=random.uniform(0, 50) if price == 0 else random.uniform(0, 150)
            )

            # Add tags
            selected_categories = random.sample(template['categories'], min(len(template['categories']), random.randint(1, 3)))
            for category_name in selected_categories:
                category_tag = next((tag for tag in tags if tag.name == category_name), None)
                if category_tag:
                    journal.marketplace_tags.add(category_tag)

            # Create journal entries
            entry_count = random.randint(*template['entry_count'])
            self.create_journal_entries(journal, entry_count, template['categories'])

            journals.append(journal)

            if i % 10 == 0:
                self.stdout.write(f'Created {i+1}/{num_journals} journals...')

        return journals

    def generate_journal_title(self, title_templates):
        """Generate realistic journal titles"""
        template = random.choice(title_templates)

        replacements = {
            'goal': random.choice(['Self-Discovery', 'Inner Peace', 'Confidence', 'Balance', 'Healing']),
            'value': random.choice(['Purpose', 'Joy', 'Strength', 'Wisdom', 'Peace']),
            'context': random.choice(['Chaos', 'Change', 'Uncertainty', 'Modern Life', 'Adversity']),
            'transition': random.choice(['Divorce', '30', 'Career Change', 'Loss', 'Moving']),
            'destination': random.choice(['Happiness', 'Success', 'Recovery', 'Freedom', 'Fulfillment']),
            'year': str(random.randint(2020, 2024)),
            'location': random.choice(['Europe', 'Southeast Asia', 'South America', 'Africa', 'New Zealand']),
            'country': random.choice(['Japan', 'Italy', 'Thailand', 'Mexico', 'Iceland']),
            'duration': random.choice(['Six-Month', 'One-Year', 'Summer', 'Gap Year']),
            'experience': random.choice(['Finding Myself', 'Adventures', 'Lessons Learned', 'Growth']),
            'region': random.choice(['Scandinavia', 'The Balkans', 'Patagonia', 'The Himalayas']),
            'parent_type': random.choice(['Mom', 'Dad', 'Parent']),
            'child_age': random.choice(['Toddlers', 'Teenagers', 'Twins']),
            'era': random.choice(['2024', 'the Digital Age', 'COVID Times']),
            'family_situation': random.choice(['Single Parenting', 'Blended Families', 'Homeschooling']),
            'business': random.choice(['My Tech Startup', 'a Creative Agency', 'an Online Store']),
            'stage': random.choice(['Early', 'Growth', 'Pivot', 'Exit']),
            'journey_type': random.choice(['The Ups and Downs', 'Lessons Learned', 'Year One']),
            'company': random.choice(['My Dream Company', 'a Social Impact Startup', 'My First Business']),
            'recovery_type': random.choice(['Addiction', 'Heartbreak', 'Loss', 'Trauma']),
            'challenge': random.choice(['Dark Times', 'Depression', 'Anxiety', 'Grief']),
            'process': random.choice(['One Day at a Time', 'The Long Road', 'Finding Hope']),
            'obstacle': random.choice(['Anxiety', 'Addiction', 'Toxic Relationships', 'Self-Doubt']),
            'art_form': random.choice(['Photography', 'Writing', 'Painting', 'Music']),
            'creation': random.choice(['Masterpiece', 'First Exhibition', 'Published Work']),
            'creative_process': random.choice(['Daily Practice', 'Inspiration Strikes', 'Breaking Blocks']),
            'medium': random.choice(['Words', 'Paint', 'Photography', 'Music'])
        }

        # Replace placeholders
        title = template
        for key, value in replacements.items():
            title = title.replace(f'{{{key}}}', value)

        return title

    def generate_journal_description(self, title, categories):
        """Generate engaging journal descriptions"""
        descriptions = {
            'Personal Growth': [
                "A raw and honest look at personal transformation, sharing the struggles and breakthroughs that led to meaningful change.",
                "Authentic reflections on self-discovery, with practical insights for anyone on their own growth journey.",
                "Personal stories of overcoming limiting beliefs and finding inner strength in challenging times."
            ],
            'Travel Adventures': [
                "Vivid accounts of cultural immersion, unexpected adventures, and the life-changing moments that only travel can bring.",
                "From planning mishaps to magical discoveries, this journal captures the real experience of exploring new places.",
                "Stories of connection, adventure, and personal growth through the lens of wanderlust."
            ],
            'Parenting': [
                "The unfiltered reality of modern parenting - from sleepless nights to proud moments and everything in between.",
                "Honest reflections on raising children in today's world, with humor, heart, and hard-won wisdom.",
                "A parent's journey through the beautiful chaos of family life, sharing both struggles and celebrations."
            ],
            'Mental Health': [
                "Courageous entries about mental health struggles and recovery, offering hope and solidarity to others facing similar challenges.",
                "A thoughtful exploration of mental wellness practices, therapy insights, and the path to emotional healing.",
                "Raw and real accounts of living with mental health challenges, breaking stigma through storytelling."
            ],
            'Entrepreneurship': [
                "Behind-the-scenes look at building a business from the ground up, including failures, pivots, and eventual success.",
                "The real story of entrepreneurship - sleepless nights, difficult decisions, and the persistence required to build something meaningful.",
                "Lessons learned from the startup trenches, offering practical wisdom for aspiring entrepreneurs."
            ],
            'Creativity': [
                "The creative process unveiled - from inspiration to finished work, including the struggles and breakthroughs along the way.",
                "An artist's journey of finding their voice, overcoming creative blocks, and embracing vulnerability through art.",
                "Stories of creative awakening and the courage to share your art with the world."
            ]
        }

        # Pick description based on primary category
        primary_category = categories[0] if categories else 'Personal Growth'
        if primary_category in descriptions:
            return random.choice(descriptions[primary_category])
        else:
            return f"A collection of personal reflections and experiences related to {title.lower()}, offering authentic insights and relatable stories for readers on similar journeys."

    def create_journal_entries(self, journal, count, categories):
        """Create realistic journal entries"""
        entry_templates = {
            'Personal Growth': [
                {"title": "The Day Everything Changed", "content": "I never thought a simple conversation could shift my entire perspective, but here we are. Today marked a turning point that I know I'll remember for years to come..."},
                {"title": "Learning to Say No", "content": "For someone who's spent most of their life as a people-pleaser, today's experience was both terrifying and liberating..."},
                {"title": "Facing My Biggest Fear", "content": "They say courage isn't the absence of fear, but action in spite of it. Today I learned what that really means..."}
            ],
            'Travel Adventures': [
                {"title": "Lost in Translation", "content": "Sometimes the best travel experiences happen when everything goes wrong. Today was one of those days..."},
                {"title": "A Stranger's Kindness", "content": "I was completely lost, didn't speak the language, and my phone was dead. Then this incredible thing happened..."},
                {"title": "Views That Change Everything", "content": "Standing at the edge of this cliff, watching the sunrise paint the landscape below, I understood why people travel..."}
            ],
            'Parenting': [
                {"title": "First Steps, Big Emotions", "content": "Watching your child take their first steps is supposed to be pure joy, right? So why am I crying?"},
                {"title": "The Tantrum That Taught Me", "content": "Public meltdowns are every parent's nightmare, but today's grocery store drama taught me something important..."},
                {"title": "Bedtime Stories and Life Lessons", "content": "It's amazing how a simple bedtime routine can become the most meaningful part of your day..."}
            ],
            'Mental Health': [
                {"title": "The Weight of Gray Days", "content": "Depression doesn't always look like sadness. Sometimes it looks like empty days and going through the motions..."},
                {"title": "Small Victories Matter", "content": "Today I got out of bed, made breakfast, and took a shower. That might not sound like much, but it's everything..."},
                {"title": "Therapy Breakthrough", "content": "I've been seeing my therapist for months, and today something finally clicked. The work is hard, but it's working..."}
            ],
            'Entrepreneurship': [
                {"title": "The Day We Almost Quit", "content": "Running a startup means facing moments where everything seems impossible. Today was one of those days..."},
                {"title": "First Sale, Real Validation", "content": "After months of building, testing, and hoping, someone actually bought our product. The feeling is indescribable..."},
                {"title": "Pivot or Persist?", "content": "Sometimes the hardest decision is knowing when to change course and when to push through..."}
            ],
            'Creativity': [
                {"title": "Creative Block, Creative Breakthrough", "content": "I've been staring at this blank canvas for weeks. Today, finally, something shifted..."},
                {"title": "The Power of Vulnerability", "content": "Sharing your creative work with the world is terrifying. Here's what happened when I finally did..."},
                {"title": "Finding My Voice", "content": "After years of trying to create like everyone else, I'm finally learning what my unique style looks like..."}
            ]
        }

        # Get templates for the primary category
        primary_category = categories[0] if categories else 'Personal Growth'
        templates = entry_templates.get(primary_category, entry_templates['Personal Growth'])

        for i in range(count):
            template = random.choice(templates)

            # Create longer, more realistic content
            content_parts = [
                template['content'],
                self.generate_entry_middle_section(primary_category),
                self.generate_entry_conclusion()
            ]

            full_content = '\n\n'.join(content_parts)

            entry_date = journal.date_published.date() + timedelta(days=random.randint(0, 60))

            JournalEntry.objects.create(
                journal=journal,
                title=template['title'],
                content=full_content,
                entry_date=entry_date,
                is_included=True
            )

    def generate_entry_middle_section(self, category):
        """Generate middle section of journal entries"""
        middle_sections = {
            'Personal Growth': [
                "The process wasn't easy. There were moments of doubt, setbacks that made me question everything, and times when giving up seemed like the only option. But something inside me refused to quit.",
                "I've learned that growth happens in the uncomfortable spaces between who we were and who we're becoming. It's messy, it's scary, and it's absolutely worth it.",
                "What struck me most was how this experience connected to everything else in my life. The patterns I'd been carrying for years suddenly became visible."
            ],
            'Travel Adventures': [
                "The locals here have a way of life that's completely different from what I'm used to. At first, it felt overwhelming, but now I'm starting to see the beauty in their approach.",
                "Travel has this way of stripping away all the things you think are important and showing you what actually matters. Today was a perfect example of that.",
                "I'm starting to realize that the best parts of traveling aren't the places you see, but the person you become while seeing them."
            ],
            'Parenting': [
                "Parenting books don't prepare you for moments like these. They give you strategies and theories, but they can't capture the complexity of real-life situations.",
                "Watching my child navigate this challenge reminded me of my own childhood and all the ways my parents shaped who I am today.",
                "Sometimes I wonder if I'm doing any of this right, but then I see the love and trust in my child's eyes, and I know we're figuring it out together."
            ],
            'Mental Health': [
                "Mental health recovery isn't linear. There are good days and bad days, breakthroughs and setbacks. Learning to be patient with the process is part of the healing.",
                "I'm beginning to understand that healing doesn't mean returning to who I was before. It means becoming someone new, someone who's integrated these experiences.",
                "The stigma around mental health makes it feel lonely sometimes, but sharing my story has connected me with others who understand."
            ],
            'Entrepreneurship': [
                "The entrepreneurial journey is unlike anything else. One day you feel like you're changing the world, the next you're questioning every decision you've ever made.",
                "What I've learned is that building a business isn't just about the product or service – it's about building yourself into the person who can lead that vision.",
                "The failure and rejection are part of the process. Each 'no' teaches you something, brings you closer to the right 'yes.'"
            ],
            'Creativity': [
                "The creative process is mysterious. You can't force inspiration, but you can show up consistently and trust that it will come.",
                "I'm learning that perfectionism is creativity's worst enemy. The magic happens when you're willing to create something imperfect.",
                "Art is ultimately about connection – connecting with yourself, your truth, and then sharing that with others who need to hear it."
            ]
        }

        sections = middle_sections.get(category, middle_sections['Personal Growth'])
        return random.choice(sections)

    def generate_entry_conclusion(self):
        """Generate conclusion paragraphs for entries"""
        conclusions = [
            "Tomorrow will bring new challenges, but I feel more prepared now. This experience has taught me something valuable about resilience.",
            "I'm grateful for this journey, even the difficult parts. They've shaped me in ways I'm only beginning to understand.",
            "Writing this down helps me process everything. Sometimes you don't know what you're feeling until you put it into words.",
            "If you're going through something similar, know that you're not alone. We're all figuring it out as we go.",
            "Life has a way of surprising you just when you think you have it all figured out. I'm learning to embrace the uncertainty.",
            "Tonight I'm reflecting on how far I've come. The journey isn't over, but I'm proud of the progress I've made."
        ]

        return random.choice(conclusions)

    def add_engagement(self, journals, users):
        """Add realistic engagement to journals"""
        self.stdout.write('Adding engagement (likes, tips, reviews)...')

        for journal in journals:
            # Add likes
            num_likes = random.randint(0, min(50, len(users)))
            likers = random.sample(users, num_likes)

            for liker in likers:
                if liker != journal.author:
                    journal.likes.add(liker)

                    # Some likes also get JournalLike records
                    if random.random() < 0.7:
                        JournalLike.objects.get_or_create(
                            user=liker,
                            journal=journal
                        )

            # Add tips for popular journals
            if journal.likes.count() > 10 or journal.price == 0:
                num_tips = random.randint(0, min(5, journal.likes.count()))
                tippers = random.sample(list(journal.likes.all()), num_tips)

                for tipper in tippers:
                    tip_amount = round(random.uniform(1.00, 10.00), 2)
                    Tip.objects.create(
                        journal=journal,
                        tipper=tipper,
                        recipient=journal.author,
                        amount=tip_amount
                    )

    def mark_featured_content(self, journals):
        """Mark some journals as featured/staff picks"""
        self.stdout.write('Marking featured content...')

        # Sort journals by engagement (likes + tips)
        journals_with_engagement = []
        for journal in journals:
            engagement_score = journal.likes.count() + (journal.total_tips / 10)
            journals_with_engagement.append((journal, engagement_score))

        journals_with_engagement.sort(key=lambda x: x[1], reverse=True)

        # Mark top 20% as staff picks
        staff_pick_count = max(1, len(journals) // 5)
        for i in range(staff_pick_count):
            journal = journals_with_engagement[i][0]
            journal.is_staff_pick = True
            journal.save()

        # Mark top 5 as featured
        for i in range(min(5, len(journals))):
            journal = journals_with_engagement[i][0]
            journal.featured = True
            journal.featured_rank = i + 1
            journal.save()

        self.stdout.write(f'Marked {staff_pick_count} staff picks and 5 featured journals')
