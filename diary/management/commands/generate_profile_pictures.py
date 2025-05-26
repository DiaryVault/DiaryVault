import os
import requests
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings
from django.db import transaction, models
import logging

logger = logging.getLogger(__name__)

# Try to import UserProfile - if it doesn't exist, we'll handle it in the save method
try:
    from diary.models import UserProfile
    HAS_USER_PROFILE = True
except ImportError:
    HAS_USER_PROFILE = False


class Command(BaseCommand):
    help = 'Generate mock profile pictures for users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--method',
            type=str,
            choices=['avatars', 'unsplash', 'generated', 'placeholder'],
            default='unsplash',  # Changed default to unsplash
            help='Method to generate profile pictures (default: unsplash)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of users to process'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing profile pictures'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )

    def handle(self, *args, **options):
        method = options['method']
        limit = options['limit']
        overwrite = options['overwrite']
        dry_run = options['dry_run']

        self.stdout.write(f"🎨 Generating profile pictures using method: {method}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Get users without profile pictures (or all if overwrite)
        users_query = User.objects.all()

        if not overwrite and HAS_USER_PROFILE:
            # Filter users who don't have profile pictures only if UserProfile exists
            try:
                users_query = users_query.filter(
                    models.Q(userprofile__profile_picture__isnull=True) |
                    models.Q(userprofile__profile_picture='')
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not filter by profile pictures: {e}"))
                self.stdout.write("Processing all users instead...")

        if limit:
            users_query = users_query[:limit]

        users = list(users_query)
        total_users = len(users)

        if total_users == 0:
            self.stdout.write(self.style.WARNING("No users found that need profile pictures"))
            return

        self.stdout.write(f"📊 Processing {total_users} users...")

        success_count = 0
        error_count = 0

        for i, user in enumerate(users, 1):
            try:
                self.stdout.write(f"Processing user {i}/{total_users}: {user.username}")

                if dry_run:
                    self.stdout.write(f"  Would generate profile picture for {user.username}")
                    success_count += 1
                    continue

                # Generate profile picture based on method
                image_file = None

                if method == 'avatars':
                    image_file = self.generate_avatar_service(user)
                elif method == 'unsplash':
                    image_file = self.generate_unsplash_image(user)
                elif method == 'generated':
                    image_file = self.generate_custom_avatar(user)
                elif method == 'placeholder':
                    image_file = self.generate_placeholder_image(user)

                if image_file:
                    # Save to user profile
                    self.save_profile_picture(user, image_file)
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✅ Generated profile picture for {user.username}")
                    )
                else:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"  ❌ Failed to generate image for {user.username}")
                    )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  ❌ Error processing {user.username}: {str(e)}")
                )
                logger.error(f"Error generating profile picture for {user.username}: {str(e)}")

        # Summary
        self.stdout.write("\n" + "="*60)
        self.stdout.write(f"🎉 Profile picture generation complete!")
        self.stdout.write(f"✅ Successful: {success_count}")
        self.stdout.write(f"❌ Errors: {error_count}")
        self.stdout.write(f"📊 Total processed: {total_users}")

    def generate_avatar_service(self, user):
        """Generate avatar using DiceBear Avatars API"""
        try:
            # Use different avatar styles
            styles = ['avataaars', 'personas', 'big-smile', 'adventurer', 'big-ears', 'bottts']
            style = random.choice(styles)

            # Use user data to make avatars somewhat consistent
            seed = user.username

            url = f"https://api.dicebear.com/7.x/{style}/png?seed={seed}&size=200"

            self.stdout.write(f"    📡 Fetching avatar from DiceBear...")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            return ContentFile(
                response.content,
                name=f"profile_{user.username}_{style}.png"
            )
        except Exception as e:
            self.stdout.write(f"    ❌ Failed to get avatar from service: {str(e)}")
            return None

    def generate_unsplash_image(self, user):
        """Generate profile picture from Unsplash"""
        try:
            # Use Unsplash's random portrait API with better categories
            categories = [
                'portrait,professional',
                'headshot,business',
                'person,formal',
                'portrait,studio',
                'headshot,corporate',
                'person,professional'
            ]
            category = random.choice(categories)

            # Use user ID for some consistency but add randomness
            random_seed = user.id * 7 + random.randint(1, 1000)
            url = f"https://source.unsplash.com/200x200/?{category}&{random_seed}"

            self.stdout.write(f"    📸 Fetching image from Unsplash...")
            response = requests.get(url, timeout=15)
            response.raise_for_status()

            return ContentFile(
                response.content,
                name=f"profile_{user.username}_unsplash.jpg"
            )
        except Exception as e:
            self.stdout.write(f"    ❌ Failed to get Unsplash image: {str(e)}")
            return None

    def generate_custom_avatar(self, user):
        """Generate a custom avatar with initials"""
        try:
            # Create a 200x200 image
            size = 200
            image = Image.new('RGB', (size, size))
            draw = ImageDraw.Draw(image)

            # Generate a random background color based on user ID
            random.seed(user.id)
            colors = [
                '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8',
                '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8C471', '#82E0AA',
                '#F1948A', '#85C1E9', '#F4D03F', '#AED6F1', '#A9DFBF'
            ]
            bg_color = random.choice(colors)

            # Fill background
            draw.rectangle([0, 0, size, size], fill=bg_color)

            # Get user initials
            first_name = user.first_name or user.username[0] if user.username else 'U'
            last_name = user.last_name or (user.username[1] if len(user.username) > 1 else '')

            initials = (first_name[0] + last_name[0]).upper() if last_name else first_name[0].upper()

            # Try to use a nice font, fall back to default
            try:
                font_size = size // 3
                # Try different font paths for different systems
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/System/Library/Fonts/Arial.ttf",
                    "/Windows/Fonts/arial.ttf",
                    "arial.ttf"
                ]
                font = None
                for font_path in font_paths:
                    try:
                        font = ImageFont.truetype(font_path, font_size)
                        break
                    except:
                        continue

                if not font:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            # Calculate text position to center it
            try:
                # For newer Pillow versions
                text_bbox = draw.textbbox((0, 0), initials, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            except AttributeError:
                # Fallback for older Pillow versions
                text_width, text_height = draw.textsize(initials, font=font)

            text_x = (size - text_width) // 2
            text_y = (size - text_height) // 2

            # Draw text
            draw.text((text_x, text_y), initials, font=font, fill='white')

            # Save to BytesIO
            output = BytesIO()
            image.save(output, format='PNG', quality=95)
            output.seek(0)

            self.stdout.write(f"    🎨 Generated custom avatar with initials: {initials}")

            return ContentFile(
                output.getvalue(),
                name=f"profile_{user.username}_generated.png"
            )

        except Exception as e:
            self.stdout.write(f"    ❌ Failed to generate custom avatar: {str(e)}")
            return None

    def generate_placeholder_image(self, user):
        """Generate a simple placeholder image"""
        try:
            # Use a placeholder service
            colors = ['FF6B6B', '4ECDC4', '45B7D1', 'FFA07A', '98D8C8']
            random.seed(user.id)
            bg_color = random.choice(colors)
            text_color = 'FFFFFF'

            initials = self.get_user_initials(user)

            url = f"https://via.placeholder.com/200x200/{bg_color}/{text_color}?text={initials}"

            self.stdout.write(f"    📡 Fetching placeholder...")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            return ContentFile(
                response.content,
                name=f"profile_{user.username}_placeholder.png"
            )
        except Exception as e:
            self.stdout.write(f"    ❌ Failed to generate placeholder: {str(e)}")
            return None

    def get_user_initials(self, user):
        """Get user initials for avatar generation"""
        first_name = user.first_name or user.username[0] if user.username else 'U'
        last_name = user.last_name or (user.username[1] if len(user.username) > 1 else '')

        initials = (first_name[0] + last_name[0]).upper() if last_name else first_name[0].upper()
        return initials

    def save_profile_picture(self, user, image_file):
        """Save the profile picture to the user's profile"""
        try:
            if HAS_USER_PROFILE:
                # Get or create user profile
                profile, created = UserProfile.objects.get_or_create(user=user)

                # Save the profile picture
                profile.profile_picture.save(
                    image_file.name,
                    image_file,
                    save=True
                )

                if created:
                    self.stdout.write(f"    📝 Created new profile for {user.username}")

                self.stdout.write(f"    💾 Saved to UserProfile: {image_file.name}")
            else:
                # Just save to media directory for now
                profile_pics_dir = os.path.join(settings.MEDIA_ROOT, 'profile_pictures')
                os.makedirs(profile_pics_dir, exist_ok=True)

                file_path = os.path.join(profile_pics_dir, image_file.name)
                with open(file_path, 'wb') as f:
                    f.write(image_file.read())

                self.stdout.write(f"    💾 Saved to: {file_path}")

        except Exception as e:
            raise Exception(f"Could not save profile picture: {str(e)}")
