import hashlib

def get_content_hash(journal_content):
    """Create a unique hash for the journal content to use as cache key"""
    return hashlib.md5(journal_content.encode('utf-8')).hexdigest()

def get_mood_emoji(mood):
    """Return appropriate emoji for a given mood."""
    mood = mood.lower()
    emoji_map = {
        'happy': '😊',
        'sad': '😢',
        'angry': '😡',
        'excited': '😃',
        'content': '😌',
        'anxious': '😰',
        'stressed': '😖',
        'relaxed': '😎',
        'proud': '🥳',
        'motivated': '💪',
        'grateful': '🙏',
        'hopeful': '✨'
        # Add more as needed
    }
    return emoji_map.get(mood, '😐')  # Default neutral emoji

def get_tag_color(tag_name):
    """
    Generate a consistent color for a tag based on its name.
    This ensures the same tag always gets the same color.
    """
    # Simple hash function to generate a number from the tag name
    tag_hash = sum(ord(c) for c in tag_name)

    # List of pleasant colors to choose from
    colors = [
        'indigo-600', 'blue-500', 'sky-500', 'cyan-500', 'teal-500',
        'emerald-500', 'green-500', 'lime-500', 'yellow-500', 'amber-500',
        'orange-500', 'red-500', 'rose-500', 'fuchsia-500', 'purple-500',
        'violet-500'
    ]

    # Use the hash to select a color
    color_index = tag_hash % len(colors)
    return colors[color_index]

def mood_to_numeric_value(mood):
    """Convert mood tag to numeric value for charting (1-10 scale)."""
    mood = mood.lower()
    mood_values = {
        'very sad': 1,
        'sad': 2,
        'disappointed': 3,
        'anxious': 4,
        'neutral': 5,
        'calm': 6,
        'content': 7,
        'happy': 8,
        'excited': 9,
        'ecstatic': 10
        # Add more as needed
    }
    return mood_values.get(mood, 5)  # Default to neutral (5)

def auto_generate_tags(content, mood=None):
    """Generate tags based on entry content and mood"""
    tags = set()

    # Common topics to check for
    topic_keywords = {
        'work': ['work', 'job', 'career', 'office', 'meeting', 'project', 'boss', 'colleague'],
        'family': ['family', 'parents', 'mom', 'dad', 'children', 'kids', 'brother', 'sister'],
        'health': ['health', 'workout', 'exercise', 'doctor', 'fitness', 'gym', 'running'],
        'food': ['food', 'dinner', 'lunch', 'breakfast', 'meal', 'cooking', 'restaurant'],
        'travel': ['travel', 'trip', 'vacation', 'journey', 'flight', 'hotel'],
        'learning': ['learning', 'study', 'read', 'book', 'class', 'course'],
        'friends': ['friend', 'social', 'party', 'hangout', 'gathering'],
        'goals': ['goal', 'plan', 'future', 'aspiration', 'dream', 'objective'],
        'reflection': ['reflection', 'thinking', 'contemplation', 'introspection', 'mindfulness']
    }

    # Convert content to lowercase for case-insensitive matching
    content_lower = content.lower()

    # Check for topic keywords in content
    for topic, keywords in topic_keywords.items():
        for keyword in keywords:
            if keyword in content_lower:
                tags.add(topic)
                break

    # Add mood as a tag if provided
    if mood:
        tags.add(mood.lower())

    return list(tags)
