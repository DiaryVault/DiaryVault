import json
import logging
import time
from datetime import datetime

# Django core
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Count, Avg
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Django REST framework
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

# Local imports
from .. import models
from ..models import Entry, Journal, Tag, JournalEntry
from ..utils.ai_helpers import generate_ai_content, generate_ai_content_personalized
from ..utils.analytics import get_content_hash, auto_generate_tags
from ..services.ai_service import AIService
from .journal_compiler import JournalAnalysisService, JournalCompilerAI
from diary.models import Web3Nonce, WalletSession
from ..serializers import (
    NonceRequestSerializer, Web3LoginSerializer, UserProfileSerializer
)
from diary.utils.Web3Utils import Web3Utils

# Initialize
User = get_user_model()
logger = logging.getLogger(__name__)

@require_POST
def demo_journal(request):
    request_id = int(time.time() * 1000)
    logger.info(f"Journal request {request_id} started")

    try:
        start_time = time.time()

        # Check content type to determine how to process the request
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle multipart form data (with file uploads)
            journal_content = request.POST.get('journal_content', '')
            photo = request.FILES.get('journal_photo')
            personalize = request.POST.get('personalize') == 'true'

            logger.info(f"Journal request {request_id} with multipart form data")
            if photo:
                logger.info(f"Photo included: {photo.name}, size: {photo.size} bytes")
        else:
            # Handle JSON data (old method)
            data = json.loads(request.body)
            journal_content = data.get('journal_content', '')
            personalize = data.get('personalize', False)
            photo = None

            logger.info(f"Journal request {request_id} with JSON data")

        if not journal_content:
            logger.warning(f"Journal request {request_id}: No content provided")
            return JsonResponse({'error': 'No content provided'}, status=400)

        # Cache key includes photo info if a photo is present
        photo_indicator = "with_photo" if photo else "no_photo"

        # If personalization is requested and user is logged in, use that
        if personalize and request.user.is_authenticated:
            # Create a unique cache key based on content, photo presence, and user
            user_id = request.user.id
            cache_key = f"journal_entry:user{user_id}:{photo_indicator}:{get_content_hash(journal_content)}"
        else:
            # Otherwise use standard cache key
            cache_key = f"journal_entry:{photo_indicator}:{get_content_hash(journal_content)}"

        # Try to get cached response
        cached_response = cache.get(cache_key)
        if cached_response and not photo:  # Don't use cache if there's a photo upload
            logger.info(f"Journal request {request_id} served from cache")
            cached_response['cache_hit'] = True
            cached_response['cache_type'] = 'server'
            cached_response['response_time'] = round(time.time() - start_time, 3)
            return JsonResponse(cached_response)

        # Generate new content if not cached
        if personalize and request.user.is_authenticated:
            # Use personalized generation
            response_data = generate_ai_content_personalized(journal_content, request.user)
        else:
            # Use standard generation
            response_data = generate_ai_content(journal_content)

        # If there's a photo, enhance the journal entry to reference it
        if photo:
            # Modify the entry to mention the photo
            entry_text = response_data.get('entry', '')
            if entry_text:
                # Add a reference to the photo at the end of the entry
                photo_reference = "\n\nI captured a special moment in a photo today. Looking at it now brings back the feelings and memories of that moment."
                response_data['entry'] = entry_text + photo_reference

        # Add metadata
        response_data['cache_hit'] = False
        response_data['cache_type'] = 'none'
        response_data['request_time'] = round(time.time() - start_time, 2)

        # Indicate if a photo was included
        response_data['has_photo'] = photo is not None

        # Cache the response (only if successful and no errors and no photo)
        if 'error' not in response_data and not photo:
            cache.set(cache_key, response_data, timeout=3600)  # Cache for 1 hour

        logger.info(f"Journal request {request_id} completed in {response_data['request_time']}s")
        return JsonResponse(response_data)

    except json.JSONDecodeError:
        logger.error(f"Journal request {request_id}: Invalid JSON in request")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Journal request {request_id} failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Server error processing your request',
            'error_details': str(e),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, status=500)

@require_POST
def regenerate_summary_ajax(request, entry_id):
    """AJAX view to regenerate an entry summary"""
    if request.method == 'POST':
        entry = get_object_or_404(Entry, id=entry_id, user=request.user)
        summary = AIService.generate_entry_summary(entry)
        return JsonResponse({'success': True, 'summary': summary})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@require_POST
def save_generated_entry(request):
    """Save a generated journal entry - supports both authenticated and anonymous users"""
    try:
        # Check content type to determine how to process the request
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle multipart form data (with file uploads)
            title = request.POST.get('title')
            content = request.POST.get('content')
            mood = request.POST.get('mood')
            tags_json = request.POST.get('tags', '[]')
            photo = request.FILES.get('journal_photo')  # Match the field name from your form
            
            # Web3 wallet data
            wallet_address = request.POST.get('wallet_address')
            chain_id = request.POST.get('chain_id')
            encrypted = request.POST.get('encrypted', 'false') == 'true'

            # Parse tags from JSON string
            try:
                tags = json.loads(tags_json)
            except json.JSONDecodeError:
                tags = []
        else:
            # Handle JSON data
            data = json.loads(request.body)
            title = data.get('title')
            content = data.get('content')
            mood = data.get('mood')
            tags = data.get('tags', [])
            photo = None
            
            # Web3 wallet data
            wallet_address = data.get('wallet_address')
            chain_id = data.get('chain_id')
            encrypted = data.get('encrypted', False)

        # Validate required fields
        if not title or not content:
            return JsonResponse({'success': False, 'error': 'Missing title or content'}, status=400)

        # Check if user is authenticated
        if request.user.is_authenticated:
            # Create entry for authenticated user
            entry = Entry.objects.create(
                user=request.user,
                title=title,
                content=content,
                mood=mood
            )

            # Save the photo if provided
            if photo:
                try:
                    from ..models import EntryPhoto
                    entry_photo = EntryPhoto.objects.create(
                        entry=entry,
                        photo=photo,
                        caption="Journal photo"
                    )
                    logger.info(f"Photo saved for entry {entry.id}")
                except Exception as e:
                    logger.error(f"Failed to save photo: {e}")

            # Add tags if provided
            if not tags and content:
                # Auto-generate tags if none were provided
                tags = auto_generate_tags(content, mood)

            if tags:
                for tag_name in tags:
                    tag, created = Tag.objects.get_or_create(
                        name=tag_name.lower().strip(),
                        user=request.user
                    )
                    entry.tags.add(tag)

            # Calculate rewards for authenticated users with wallet
            word_count = len(content.split())
            base_reward = word_count // 10  # 1 token per 10 words
            wallet_bonus = 5 if wallet_address else 0
            total_rewards = base_reward + wallet_bonus

            # Clear any pending entry from session
            if 'pending_entry' in request.session:
                del request.session['pending_entry']

            return JsonResponse({
                'success': True,
                'entry_id': entry.id,
                'rewards': total_rewards,
                'redirect_url': f'/entry/{entry.id}/',
                'message': 'Entry saved successfully!'
            })
        else:
            # For anonymous users, save to session
            import uuid
            
            # Generate a temporary ID
            temp_id = str(uuid.uuid4())
            
            # Create session entry data
            session_entry = {
                'id': temp_id,
                'title': title,
                'content': content,
                'mood': mood,
                'tags': tags,
                'wallet_address': wallet_address,
                'chain_id': chain_id,
                'created_at': timezone.now().isoformat(),
                'is_encrypted': encrypted,
                'had_photo': photo is not None
            }
            
            # Store in session
            if 'anonymous_entries' not in request.session:
                request.session['anonymous_entries'] = []
            
            request.session['anonymous_entries'].append(session_entry)
            request.session['pending_entry'] = session_entry  # Also store as pending for login
            request.session.modified = True
            
            # Calculate mock rewards
            word_count = len(content.split())
            base_reward = word_count // 10
            wallet_bonus = 5 if wallet_address else 0
            total_rewards = base_reward + wallet_bonus
            
            return JsonResponse({
                'success': True,
                'entry_id': temp_id,
                'rewards': total_rewards,
                'is_anonymous': True,
                'message': 'Entry saved temporarily. Sign up to save permanently and earn real rewards!',
                'redirect_url': None,  # Don't redirect for anonymous users
                'auth_required': True,
                'login_url': '/login/?save_after_login=true',
                'signup_url': '/signup/?feature=journal'
            })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error saving generated entry: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Server error while saving entry',
            'details': str(e) if settings.DEBUG else 'Please try again'
        }, status=500)

@require_POST
@login_required
def chat_with_ai(request):
    """
    Handle ongoing chat conversation with AI for journal creation
    """
    request_id = int(time.time() * 1000)
    logger.info(f"Chat request {request_id} started")

    try:
        start_time = time.time()

        # Parse request data
        if request.content_type and 'multipart/form-data' in request.content_type:
            user_message = request.POST.get('message', '')
            conversation_history = request.POST.get('conversation_history', '[]')
            chat_mode = request.POST.get('chat_mode', 'free-form')

            # Check for photo with multiple possible field names
            photo = None
            for field_name in ['photo', 'entry_photo', 'journal_photo']:
                if field_name in request.FILES:
                    photo = request.FILES[field_name]
                    logger.info(f"Photo found with field name: {field_name}")
                    break

            # Validate photo if present
            if photo:
                # Check file size (5MB limit)
                if photo.size > 5 * 1024 * 1024:
                    return JsonResponse({'error': 'Image file is too large. Please select an image under 5MB.'}, status=400)

                # Check file type
                if not photo.content_type.startswith('image/'):
                    return JsonResponse({'error': 'Only image files are allowed.'}, status=400)

                logger.info(f"Valid photo uploaded: {photo.name}, size: {photo.size} bytes")
        else:
            data = json.loads(request.body)
            user_message = data.get('message', '')
            conversation_history = data.get('conversation_history', [])
            chat_mode = data.get('chat_mode', 'free-form')
            photo = None

        if not user_message and not photo:
            return JsonResponse({'error': 'Please provide a message or photo'}, status=400)

        # Parse conversation history if it's a string
        if isinstance(conversation_history, str):
            try:
                conversation_history = json.loads(conversation_history)
            except json.JSONDecodeError:
                conversation_history = []

        # Count user messages to determine conversation stage
        user_message_count = len([msg for msg in conversation_history if msg.get('role') == 'user'])

        # Determine if we should generate journal entry
        should_generate_entry = (
            user_message_count >= 2 or  # After 2+ user messages
            len(user_message.split()) > 50 or  # Long message
            any(word in user_message.lower() for word in ['create', 'generate', 'write', 'journal', 'entry'])
        )

        if should_generate_entry:
            # Generate journal entry
            journal_data = generate_journal_entry_from_conversation(
                conversation_history + [{'role': 'user', 'content': user_message}],
                chat_mode,
                photo
            )

            response_data = {
                'type': 'journal_entry',
                'ai_message': "I've created a personalized journal entry based on our conversation!",
                'should_switch_to_form': True,
                'journal_entry': journal_data,
                'photo_uploaded': photo is not None
            }
        else:
            # Continue conversation
            ai_response = generate_conversation_response(user_message, conversation_history, chat_mode)

            response_data = {
                'type': 'conversation',
                'ai_message': ai_response,
                'should_switch_to_form': False,
                'conversation_suggestions': generate_follow_up_suggestions(user_message, chat_mode),
                'photo_uploaded': photo is not None
            }

        # Add metadata
        response_data['request_time'] = round(time.time() - start_time, 2)
        response_data['request_id'] = request_id

        logger.info(f"Chat request {request_id} completed in {response_data['request_time']}s, photo: {photo is not None}")
        return JsonResponse(response_data)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Chat request {request_id} failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Server error processing your request',
            'error_details': str(e) if settings.DEBUG else 'Please try again',
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, status=500)

def generate_journal_entry_from_conversation(conversation_history, chat_mode, photo=None):
    """Generate a journal entry from conversation history"""

    # Extract user messages
    user_messages = [msg['content'] for msg in conversation_history if msg.get('role') == 'user']
    combined_content = '\n\n'.join(user_messages)

    # Simple but effective journal generation
    if chat_mode == 'daily-reflection':
        title = f"Daily Reflection - {datetime.now().strftime('%B %d')}"
        entry_content = generate_reflection_entry(combined_content)
    elif chat_mode == 'gratitude-practice':
        title = f"Gratitude Journal - {datetime.now().strftime('%B %d')}"
        entry_content = generate_gratitude_entry(combined_content)
    elif chat_mode == 'goal-tracking':
        title = f"Progress Update - {datetime.now().strftime('%B %d')}"
        entry_content = generate_goal_entry(combined_content)
    else:
        title = f"Today's Thoughts - {datetime.now().strftime('%B %d')}"
        entry_content = generate_general_entry(combined_content)

    return {
        'title': title,
        'entry': entry_content,
        'mood': 'content',  # Default mood
        'tags': extract_tags_from_content(combined_content)
    }


def generate_reflection_entry(content):
    """Generate a reflection-style journal entry"""
    return f"""Today was a day worth reflecting on. {content}

Looking back on these experiences, I'm struck by how much growth happens in the small moments. Each interaction, each challenge, each moment of joy contributes to who I'm becoming.

I'm grateful for the opportunity to pause and reflect on these experiences. They remind me that life is happening right now, in these everyday moments that might seem ordinary but are actually quite extraordinary."""


def generate_gratitude_entry(content):
    """Generate a gratitude-focused journal entry"""
    return f"""I'm taking a moment today to focus on gratitude. {content}

There's something powerful about intentionally noticing what I'm thankful for. It shifts my perspective and reminds me of the abundance that's already present in my life.

These moments of gratitude don't just make me feel better in the moment - they're slowly changing how I see the world. I'm learning to notice beauty and kindness more readily, and that's a gift that keeps giving."""


def generate_goal_entry(content):
    """Generate a goal-tracking journal entry"""
    return f"""Today I made progress on what matters to me. {content}

Every step forward, no matter how small, is worth celebrating. I'm learning that consistency matters more than perfection, and that progress isn't always linear.

Looking at where I am now compared to where I started, I can see the growth happening. It motivates me to keep moving forward, one day at a time."""


def generate_general_entry(content):
    """Generate a general journal entry"""
    return f"""Today brought its own unique mix of experiences. {content}

I'm constantly amazed by how much can happen in a single day - the thoughts, feelings, interactions, and moments that make up the fabric of life. Writing about it helps me process and appreciate it all.

These ordinary days are actually quite extraordinary when I take the time to really notice them."""


def extract_tags_from_content(content):
    """Extract relevant tags from the content"""
    content_lower = content.lower()
    tags = []

    # Common tag categories
    tag_keywords = {
        'work': ['work', 'job', 'career', 'office', 'meeting', 'project'],
        'family': ['family', 'mom', 'dad', 'sister', 'brother', 'parent', 'child'],
        'friends': ['friend', 'friends', 'social', 'hang out', 'party'],
        'health': ['exercise', 'workout', 'health', 'doctor', 'medical', 'fitness'],
        'gratitude': ['grateful', 'thankful', 'appreciate', 'blessed'],
        'reflection': ['reflect', 'think', 'realize', 'understand', 'learn'],
        'goals': ['goal', 'achievement', 'accomplish', 'progress', 'success'],
        'creativity': ['create', 'art', 'music', 'write', 'design', 'creative'],
        'travel': ['travel', 'trip', 'vacation', 'journey', 'visit'],
        'food': ['food', 'eat', 'cook', 'restaurant', 'meal', 'dinner']
    }

    for tag, keywords in tag_keywords.items():
        if any(keyword in content_lower for keyword in keywords):
            tags.append(tag)

    return ', '.join(tags[:5])  # Limit to 5 tags


def generate_conversation_response(user_message, conversation_history, chat_mode):
    """Generate a conversation response to keep the chat going"""

    user_message_count = len([msg for msg in conversation_history if msg.get('role') == 'user'])

    if user_message_count == 0:  # First message
        return get_first_response(user_message, chat_mode)
    elif user_message_count == 1:  # Second user message
        return get_follow_up_response(user_message, chat_mode)
    else:
        return get_deeper_response(user_message, chat_mode)


def get_first_response(user_message, chat_mode):
    """Generate first response based on chat mode"""
    responses = {
        'daily-reflection': [
            "That's really interesting! I can sense there's more to explore there. What emotions came up for you during that experience?",
            "I love how you described that. Can you tell me more about what made that moment particularly meaningful for you?",
            "That sounds like it had quite an impact on you. What thoughts have been staying with you since then?"
        ],
        'gratitude-practice': [
            "That's beautiful - I can feel the appreciation in your words. What is it about that experience that touches your heart most?",
            "I love hearing about what you're grateful for. How does focusing on that gratitude change how you feel?",
            "That's wonderful. Can you share what made you pause and really notice that moment of gratitude?"
        ],
        'goal-tracking': [
            "That sounds like meaningful progress! What do you think made the difference in moving forward today?",
            "I love hearing about your achievements. How does this progress connect to your bigger goals?",
            "That's fantastic! What did you learn about yourself through that experience?"
        ],
        'free-form': [
            "Thank you for sharing that with me. I'm curious - what part of that experience is still on your mind?",
            "That sounds really significant. Can you tell me more about how that made you feel?",
            "I can tell this means something important to you. What would you like to explore more deeply?"
        ]
    }

    mode_responses = responses.get(chat_mode, responses['free-form'])
    import random
    return random.choice(mode_responses)


def get_follow_up_response(user_message, chat_mode):
    """Generate follow-up response"""
    responses = [
        "That's really insightful. I'm getting a clearer picture of your day. Is there anything else that stands out to you?",
        "I appreciate how thoughtfully you're sharing this. What other moments from today feel worth exploring?",
        "You're painting such a vivid picture of your experience. What else would you like to capture about today?",
        "This is really meaningful. Are there other aspects of your day that you'd like to reflect on?"
    ]

    import random
    return random.choice(responses)


def get_deeper_response(user_message, chat_mode):
    """Generate deeper response for later in conversation"""
    responses = [
        "I feel like I'm really understanding your day now. You've shared such rich details about your experiences.",
        "This conversation has given me a wonderful sense of who you are and how you experience life.",
        "Thank you for being so open and thoughtful in sharing these experiences with me.",
        "I'm really enjoying this conversation. You have such interesting perspectives on your daily life."
    ]

    import random
    return random.choice(responses)


def generate_follow_up_suggestions(user_message, chat_mode):
    """Generate follow-up suggestions for the conversation"""
    suggestions = {
        'daily-reflection': [
            "Tell me about a challenge you faced today",
            "What was the highlight of your day?",
            "How are you feeling right now?",
            "What did you learn about yourself today?"
        ],
        'gratitude-practice': [
            "What small moment brought you joy?",
            "Who made a positive impact on your day?",
            "What are you most thankful for?",
            "How has gratitude changed your perspective?"
        ],
        'goal-tracking': [
            "What progress did you make today?",
            "What motivated you to keep going?",
            "What obstacles did you overcome?",
            "How will you build on today's progress?"
        ],
        'free-form': [
            "What else is on your mind?",
            "How are you feeling about everything?",
            "What would you like to remember about today?",
            "Is there anything else you'd like to explore?"
        ]
    }

    mode_suggestions = suggestions.get(chat_mode, suggestions['free-form'])
    import random
    return random.sample(mode_suggestions, min(3, len(mode_suggestions)))

# JOURNAL COMPILER API ENDPOINTS

@login_required
@require_POST
def analyze_entries_ajax(request):
    """AJAX endpoint to analyze entries for compilation - matches your journal_compiler"""
    try:
        data = json.loads(request.body)
        compilation_method = data.get('method', 'ai')
        entry_ids = data.get('entry_ids', [])

        # Get selected entries or all entries if none selected
        if entry_ids:
            entries = Entry.objects.filter(
                id__in=entry_ids,
                user=request.user
            )
        else:
            entries = Entry.objects.filter(user=request.user)

        # Perform analysis based on compilation method
        if compilation_method == 'ai':
            analysis = JournalCompilerAI.smart_analyze_entries(request.user, entries)
        elif compilation_method == 'thematic':
            analysis = JournalCompilerAI.thematic_analyze_entries(request.user, entries)
        elif compilation_method == 'chronological':
            analysis = JournalCompilerAI.chronological_analyze_entries(request.user, entries)
        else:
            analysis = JournalAnalysisService.analyze_user_entries(request.user, entries)

        return JsonResponse({
            'success': True,
            'analysis': analysis,
            'entry_count': entries.count()
        })

    except Exception as e:
        logger.error(f"Error analyzing entries: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to analyze entries'
        }, status=500)

@login_required
@require_POST
def generate_journal_structure(request):
    """Generate journal structure with AI-powered chapters and organization"""
    try:
        data = json.loads(request.body)

        compilation_method = data.get('method', 'ai')
        journal_type = data.get('journal_type', 'growth')
        entry_ids = data.get('entry_ids', [])
        ai_enhancements = data.get('ai_enhancements', [])

        # Get entries
        entries = Entry.objects.filter(
            id__in=entry_ids,
            user=request.user
        ) if entry_ids else Entry.objects.filter(user=request.user)

        if not entries.exists():
            return JsonResponse({
                'success': False,
                'error': 'No entries selected'
            }, status=400)

        # Generate journal structure using AI
        structure = JournalCompilerAI.generate_journal_structure(
            user=request.user,
            entries=entries,
            compilation_method=compilation_method,
            journal_type=journal_type,
            ai_enhancements=ai_enhancements
        )

        # Store structure in session for later use
        request.session['journal_structure'] = structure
        request.session['selected_entry_ids'] = list(entries.values_list('id', flat=True))

        return JsonResponse({
            'success': True,
            'structure': structure,
            'estimated_length': structure.get('estimated_length', 0),
            'suggested_price': structure.get('suggested_price', 9.99)
        })

    except Exception as e:
        logger.error(f"Error generating journal structure: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to generate journal structure'
        }, status=500)

@login_required
@require_POST
def publish_compiled_journal(request):
    """Publish the compiled journal to marketplace"""
    try:
        data = json.loads(request.body)

        title = data.get('title')
        description = data.get('description')
        price = float(data.get('price', 0))

        # Get structure from session
        structure = request.session.get('journal_structure')
        entry_ids = request.session.get('selected_entry_ids')

        if not structure or not entry_ids:
            return JsonResponse({
                'success': False,
                'error': 'Journal structure not found. Please regenerate.'
            }, status=400)

        # Create the journal
        journal = JournalCompilerAI.create_compiled_journal(
            user=request.user,
            title=title,
            description=description,
            price=price,
            structure=structure,
            entry_ids=entry_ids
        )

        # Clear session data
        if 'journal_structure' in request.session:
            del request.session['journal_structure']
        if 'selected_entry_ids' in request.session:
            del request.session['selected_entry_ids']

        return JsonResponse({
            'success': True,
            'journal_id': journal.id,
            'redirect_url': f'/marketplace/journal/{journal.id}/'
        })

    except Exception as e:
        logger.error(f"Error publishing compiled journal: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@require_POST
def quick_analyze_for_publishing(request):
    """Quick analysis API for publishing decisions"""
    try:
        data = json.loads(request.body)
        entry_ids = data.get('entry_ids', [])

        if not entry_ids:
            # Analyze all user entries
            entries = Entry.objects.filter(user=request.user)
        else:
            entries = Entry.objects.filter(id__in=entry_ids, user=request.user)

        if not entries.exists():
            return JsonResponse({
                'success': False,
                'error': 'No entries found'
            }, status=400)

        # Quick analysis
        analysis = {
            'total_entries': entries.count(),
            'total_words': sum(len(entry.content.split()) for entry in entries),
            'avg_length': 0,
            'themes': [],
            'quality_indicators': {},
            'publishability_score': 0
        }

        if entries.exists():
            analysis['avg_length'] = analysis['total_words'] / analysis['total_entries']

            # Extract themes
            theme_counter = {}
            for entry in entries:
                for tag in entry.tags.all():
                    theme_counter[tag.name] = theme_counter.get(tag.name, 0) + 1

            analysis['themes'] = [
                {'name': theme, 'count': count}
                for theme, count in sorted(theme_counter.items(), key=lambda x: x[1], reverse=True)[:5]
            ]

            # Quality indicators
            entries_with_tags = entries.filter(tags__isnull=False).distinct().count()
            entries_with_mood = entries.exclude(mood__isnull=True).count()

            analysis['quality_indicators'] = {
                'has_tags': entries_with_tags / analysis['total_entries'] * 100,
                'has_mood': entries_with_mood / analysis['total_entries'] * 100,
                'good_length': sum(1 for entry in entries if len(entry.content.split()) >= 100) / analysis['total_entries'] * 100
            }

            # Simple publishability score
            score = 0
            if analysis['total_entries'] >= 10:
                score += 25
            elif analysis['total_entries'] >= 5:
                score += 15

            if analysis['avg_length'] >= 150:
                score += 25
            elif analysis['avg_length'] >= 75:
                score += 15

            if len(analysis['themes']) >= 3:
                score += 25
            elif len(analysis['themes']) >= 1:
                score += 15

            if analysis['quality_indicators']['has_tags'] >= 50:
                score += 25
            elif analysis['quality_indicators']['has_tags'] >= 25:
                score += 15

            analysis['publishability_score'] = min(100, score)

        return JsonResponse({
            'success': True,
            'analysis': analysis,
            'recommendations': _get_publishing_recommendations(analysis)
        })

    except Exception as e:
        logger.error(f"Error in quick analysis: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Analysis failed'
        }, status=500)

@login_required
@require_POST
def get_price_suggestion(request):
    """API endpoint for AI-powered price suggestions"""
    try:
        data = json.loads(request.body)
        entry_ids = data.get('entry_ids', [])
        journal_type = data.get('journal_type', 'growth')
        target_audience = data.get('target_audience', 'general')

        entries = Entry.objects.filter(id__in=entry_ids, user=request.user) if entry_ids else Entry.objects.filter(user=request.user)

        if not entries.exists():
            return JsonResponse({
                'success': False,
                'error': 'No entries found'
            }, status=400)

        # Analyze entries for pricing
        analysis = JournalAnalysisService.analyze_user_entries(request.user, entries)

        # Calculate suggested price
        base_price = 4.99

        # Quality multiplier
        quality_score = analysis.get('quality_score', {}).get('score', 50)
        quality_multiplier = 1 + (quality_score - 50) / 200

        # Length multiplier
        total_words = sum(len(entry.content.split()) for entry in entries)
        if total_words > 15000:
            length_multiplier = 1.6
        elif total_words > 10000:
            length_multiplier = 1.4
        elif total_words > 5000:
            length_multiplier = 1.2
        else:
            length_multiplier = 1.0

        # Theme/market multiplier
        theme_multipliers = {
            'travel': 1.3,
            'growth': 1.2,
            'career': 1.25,
            'relationships': 1.15,
            'creativity': 1.2,
            'health': 1.1
        }
        market_multiplier = theme_multipliers.get(journal_type, 1.0)

        suggested_price = base_price * quality_multiplier * length_multiplier * market_multiplier

        # Round to reasonable price points
        price_points = [2.99, 4.99, 6.99, 9.99, 12.99, 14.99, 19.99, 24.99]
        final_price = min(price_points, key=lambda x: abs(x - suggested_price))

        # Get market comparisons
        similar_journals = Journal.objects.filter(
            is_published=True
        ).aggregate(
            avg_price=Avg('price'),
            min_price=models.Min('price'),
            max_price=models.Max('price')
        )

        return JsonResponse({
            'success': True,
            'suggested_price': final_price,
            'price_range': {
                'min': max(0.99, final_price * 0.7),
                'max': min(29.99, final_price * 1.5)
            },
            'market_data': {
                'average_price': round(similar_journals['avg_price'] or 9.99, 2),
                'price_range': f"${similar_journals['min_price'] or 0.99:.2f} - ${similar_journals['max_price'] or 24.99:.2f}"
            },
            'factors': {
                'quality_score': quality_score,
                'total_words': total_words,
                'journal_type': journal_type,
                'entry_count': entries.count()
            }
        })

    except Exception as e:
        logger.error(f"Error getting price suggestion: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Price suggestion failed'
        }, status=500)

@login_required
@require_POST
def generate_marketing_copy(request):
    """Generate AI-powered marketing copy for a journal"""
    try:
        data = json.loads(request.body)
        title = data.get('title', '')
        description = data.get('description', '')
        journal_type = data.get('journal_type', 'growth')
        entry_ids = data.get('entry_ids', [])

        if not title:
            return JsonResponse({
                'success': False,
                'error': 'Title is required'
            }, status=400)

        # Create a temporary journal object for analysis
        class TempJournal:
            def __init__(self, title, description, author, journal_type):
                self.title = title
                self.description = description
                self.author = author
                self.journal_type = journal_type
                self.entries = Entry.objects.filter(id__in=entry_ids, user=author) if entry_ids else Entry.objects.filter(user=author)

        temp_journal = TempJournal(title, description, request.user, journal_type)

        # Generate marketing copy using AI
        marketing_data = AIService.generate_marketing_copy(temp_journal)

        # Parse the marketing copy if it's a string
        marketing_copy = marketing_data.get('marketing_copy', '')

        # Extract different components (simplified parsing)
        lines = marketing_copy.split('\n')
        parsed_copy = {
            'tagline': f'Discover the transformative power of {journal_type}',
            'short_description': description[:80] + '...' if len(description) > 80 else description,
            'social_media': f'New journal: "{title}" - A personal journey of {journal_type} and discovery. #journaling #personal{journal_type}',
            'email_subject': f'📖 New Release: {title}'
        }

        # Try to extract better components from AI response
        for line in lines:
            line = line.strip()
            if line.startswith('Tagline:') or line.startswith('1.'):
                parsed_copy['tagline'] = line.split(':', 1)[-1].strip().strip('"')
            elif line.startswith('Short description:') or line.startswith('2.'):
                parsed_copy['short_description'] = line.split(':', 1)[-1].strip().strip('"')
            elif line.startswith('Social media:') or line.startswith('3.'):
                parsed_copy['social_media'] = line.split(':', 1)[-1].strip().strip('"')
            elif line.startswith('Email subject:') or line.startswith('4.'):
                parsed_copy['email_subject'] = line.split(':', 1)[-1].strip().strip('"')

        return JsonResponse({
            'success': True,
            'marketing_copy': parsed_copy,
            'full_ai_response': marketing_copy
        })

    except Exception as e:
        logger.error(f"Error generating marketing copy: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Marketing copy generation failed'
        }, status=500)

@login_required
def get_journal_templates_api(request):
    """API endpoint to get available journal templates"""
    try:
        from .journal_compiler import JournalTemplateService
        templates = JournalTemplateService.get_available_templates()

        return JsonResponse({
            'success': True,
            'templates': templates
        })

    except Exception as e:
        logger.error(f"Error getting templates: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to load templates'
        }, status=500)

@login_required
@require_POST
def save_journal_draft(request):
    """Save journal compilation as draft"""
    try:
        data = json.loads(request.body)

        # Store draft in session or database
        draft_data = {
            'title': data.get('title', ''),
            'description': data.get('description', ''),
            'journal_type': data.get('journal_type', 'growth'),
            'compilation_method': data.get('compilation_method', 'ai'),
            'selected_entries': data.get('entry_ids', []),
            'ai_enhancements': data.get('ai_enhancements', []),
            'structure': data.get('structure', {}),
            'saved_at': timezone.now().isoformat()
        }

        # Save to session for now (you could create a JournalDraft model)
        request.session['journal_draft'] = draft_data

        return JsonResponse({
            'success': True,
            'message': 'Draft saved successfully',
            'draft_id': 'session_draft'  # You could generate actual IDs with a model
        })

    except Exception as e:
        logger.error(f"Error saving draft: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to save draft'
        }, status=500)

@login_required
def load_journal_draft(request):
    """Load saved journal draft"""
    try:
        draft_data = request.session.get('journal_draft')

        if not draft_data:
            return JsonResponse({
                'success': False,
                'error': 'No draft found'
            }, status=404)

        return JsonResponse({
            'success': True,
            'draft': draft_data
        })

    except Exception as e:
        logger.error(f"Error loading draft: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to load draft'
        }, status=500)

@login_required
@require_POST
def validate_journal_data(request):
    """Validate journal data before publishing"""
    try:
        data = json.loads(request.body)

        errors = []
        warnings = []

        # Validate title
        title = data.get('title', '').strip()
        if not title:
            errors.append('Title is required')
        elif len(title) < 5:
            warnings.append('Title might be too short for good discoverability')
        elif len(title) > 100:
            errors.append('Title is too long (max 100 characters)')

        # Validate description
        description = data.get('description', '').strip()
        if not description:
            errors.append('Description is required')
        elif len(description) < 50:
            warnings.append('Description should be at least 50 characters for better engagement')
        elif len(description) > 500:
            warnings.append('Description might be too long for marketplace listings')

        # Validate price
        try:
            price = float(data.get('price', 0))
            if price < 0:
                errors.append('Price cannot be negative')
            elif price > 99.99:
                warnings.append('Price seems unusually high - consider market research')
        except ValueError:
            errors.append('Invalid price format')

        # Validate entries
        entry_ids = data.get('entry_ids', [])
        if not entry_ids:
            errors.append('At least one entry must be selected')
        else:
            entries = Entry.objects.filter(id__in=entry_ids, user=request.user)
            if entries.count() != len(entry_ids):
                errors.append('Some selected entries not found')

            # Check entry quality
            short_entries = sum(1 for entry in entries if len(entry.content.split()) < 50)
            if short_entries > len(entry_ids) * 0.3:
                warnings.append('Many entries are quite short - consider expanding or removing them')

        # Check for duplicate titles
        if title:
            existing = Journal.objects.filter(
                title__iexact=title,
                author=request.user,
                is_published=True
            ).exists()
            if existing:
                errors.append('You already have a published journal with this title')

        return JsonResponse({
            'success': True,
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        })

    except Exception as e:
        logger.error(f"Error validating journal data: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Validation failed'
        }, status=500)

# HELPER FUNCTIONS FOR CHAT FUNCTIONALITY

def generate_chat_response(user_message, conversation_history, chat_mode, user=None, photo=None):
    """
    Generate AI response for chat conversation
    """

    # Build conversation context for the LLM
    conversation_context = build_conversation_context(
        user_message=user_message,
        conversation_history=conversation_history,
        chat_mode=chat_mode,
        user=user,
        photo=photo
    )

    # Determine if we should generate a journal entry or continue chatting
    should_generate_entry = should_create_journal_entry(conversation_history, user_message)

    if should_generate_entry:
        # Generate final journal entry
        journal_data = generate_final_journal_entry(conversation_history, user_message, user)
        return {
            'type': 'journal_entry',
            'ai_message': "Perfect! I've created a beautiful journal entry based on our conversation. You can review and edit it below.",
            'journal_entry': journal_data,
            'should_switch_to_form': True
        }
    else:
        # Continue conversation
        ai_message = generate_conversational_response(conversation_context)
        return {
            'type': 'conversation',
            'ai_message': ai_message,
            'should_switch_to_form': False,
            'conversation_suggestions': generate_conversation_suggestions(conversation_context)
        }

def build_conversation_context(user_message, conversation_history, chat_mode, user, photo):
    """
    Build comprehensive context for the LLM
    """

    # Create a rich system prompt based on chat mode and user history
    system_prompt = create_dynamic_system_prompt(chat_mode, user)

    # Build conversation summary
    conversation_summary = summarize_conversation(conversation_history)

    # Analyze user's writing style from conversation
    writing_style = analyze_writing_style(conversation_history)

    # Photo context
    photo_context = "The user has shared a photo with this message." if photo else ""

    context = {
        'system_prompt': system_prompt,
        'conversation_summary': conversation_summary,
        'writing_style': writing_style,
        'current_message': user_message,
        'photo_context': photo_context,
        'chat_mode': chat_mode,
        'message_count': len([msg for msg in conversation_history if msg.get('role') == 'user'])
    }

    return context

def create_dynamic_system_prompt(chat_mode, user):
    """
    Create a dynamic system prompt based on mode and user preferences
    """

    base_prompt = """You are an empathetic and insightful journal assistant. Your role is to help users explore their thoughts, feelings, and experiences through meaningful conversation. You ask thoughtful follow-up questions, show genuine interest in their responses, and help them dive deeper into their experiences.

Key principles:
- Be genuinely curious about their experiences
- Ask one thoughtful follow-up question at a time
- Validate their feelings and experiences
- Help them explore emotions and insights
- Use their natural language style
- Be conversational and warm, not clinical or robotic"""

    mode_specific_prompts = {
        'daily-reflection': """
Focus on helping them reflect on their day. Ask about:
- Key moments and experiences
- Emotional highs and lows
- What they learned or realized
- How they handled challenges
- What they're grateful for
- How they're feeling about tomorrow
""",
        'gratitude-practice': """
Focus on gratitude and positive experiences. Ask about:
- What brought them joy today
- People who made a positive impact
- Small moments they appreciated
- Things they often take for granted
- How gratitude affects their perspective
- Ways to carry this appreciation forward
""",
        'goal-tracking': """
Focus on progress, achievements, and aspirations. Ask about:
- What they accomplished today
- Steps toward their bigger goals
- Obstacles they overcame
- Skills they're developing
- What motivated them to keep going
- How they want to build on today's progress
""",
        'free-form': """
Follow their lead completely. Ask about whatever seems most important to them:
- What's really on their mind
- What they most want to explore or understand
- Feelings or experiences that stand out
- Anything they want to process or remember
"""
    }

    mode_prompt = mode_specific_prompts.get(chat_mode, mode_specific_prompts['free-form'])

    # Add user-specific context if available
    user_context = ""
    if user and user.is_authenticated:
        # Get user's previous entries for context
        recent_entries = Entry.objects.filter(user=user).order_by('-created_at')[:3]
        if recent_entries:
            user_context = f"\nContext: This user has written {recent_entries.count()} recent entries. Their recent topics include themes around personal growth and daily experiences."

    return base_prompt + mode_prompt + user_context

def should_create_journal_entry(conversation_history, current_message):
    """
    Determine if we have enough content for a journal entry
    """

    # Use the simpler decision method from AIService
    should_create, reason = AIService.generate_chat_decision(conversation_history, current_message)

    logger.info(f"Journal entry decision: {should_create} - {reason}")
    return should_create

def generate_conversational_response(conversation_context):
    """
    Generate a natural, conversational AI response
    """

    # Create a focused prompt for conversation
    conversation_prompt = f"""
You are a warm, empathetic journal assistant having a natural conversation with someone about their day and experiences.

Chat Mode: {conversation_context['chat_mode']}
Message Count: {conversation_context['message_count']}

Their latest message: "{conversation_context['current_message']}"

Recent conversation: {conversation_context['conversation_summary']}

Generate a warm, engaging response that:
1. Acknowledges what they shared with genuine interest
2. Asks ONE thoughtful follow-up question to explore deeper
3. Feels natural and conversational (like talking to a caring friend)
4. Avoids being clinical or overly formal

Keep your response to 1-2 sentences plus one follow-up question.
"""

    # Use your existing AI service
    try:
        response = AIService.generate_conversational_response(conversation_prompt)

        # Ensure we have a reasonable response
        if not response or len(response.strip()) < 10:
            # Fallback responses based on chat mode
            fallback_responses = {
                'daily-reflection': "That sounds really meaningful. What made that moment stand out to you?",
                'gratitude-practice': "I love hearing about what brings you joy. How did that make you feel?",
                'goal-tracking': "That's great progress! What motivated you to keep going?",
                'free-form': "Thank you for sharing that with me. What's been on your mind about it?"
            }

            mode = conversation_context.get('chat_mode', 'free-form')
            response = fallback_responses.get(mode, "I'd love to hear more about that. What stood out to you most?")

        return response

    except Exception as e:
        logger.error(f"Error generating conversational response: {e}")
        # Return a safe fallback
        return "That's really interesting. Can you tell me more about how that made you feel?"

def generate_final_journal_entry(conversation_history, final_message, user):
    """
    Generate the final journal entry from the entire conversation
    """

    # Combine all user messages
    user_content = extract_user_content_from_conversation(conversation_history, final_message)

    # Analyze their writing style
    writing_style = analyze_writing_style(conversation_history)

    # Create comprehensive prompt
    journal_prompt = f"""
Create a personal journal entry based on this conversation. The person has shared their thoughts and experiences naturally through our chat.

Their messages:
{user_content}

Writing style to match:
{writing_style}

Create a journal entry that:
- Sounds like THEY wrote it, not an AI
- Captures the essence of what they shared
- Uses their natural language and tone
- Flows naturally from their thoughts
- Includes the specific details and emotions they mentioned
- Feels authentic and personal

Start the entry naturally - avoid cliché openings like "As I sit down to reflect..."

Make it feel like their authentic voice and experience.
"""

    # Generate using your existing AI service
    if user and user.is_authenticated:
        journal_data = generate_ai_content_personalized(journal_prompt, user)
    else:
        journal_data = generate_ai_content(journal_prompt)

    return journal_data

def analyze_writing_style(conversation_history):
    """
    Analyze the user's writing style from their messages
    """

    user_messages = [msg.get('content', '') for msg in conversation_history if msg.get('role') == 'user']

    if not user_messages:
        return "casual and conversational"

    all_text = ' '.join(user_messages)

    style_analysis = {
        'length': 'concise' if len(all_text) < 200 else 'detailed',
        'tone': analyze_tone(all_text),
        'emotion_level': analyze_emotion_level(all_text),
        'complexity': analyze_complexity(all_text)
    }

    return f"{style_analysis['tone']}, {style_analysis['emotion_level']}, tends to be {style_analysis['length']}"

def analyze_tone(text):
    """Analyze conversational tone"""
    casual_indicators = ['like', 'yeah', 'really', 'kinda', 'gonna', 'wanna']
    formal_indicators = ['however', 'therefore', 'consequently', 'furthermore']

    casual_count = sum(1 for word in casual_indicators if word in text.lower())
    formal_count = sum(1 for word in formal_indicators if word in text.lower())

    if casual_count > formal_count:
        return 'casual'
    elif formal_count > casual_count:
        return 'formal'
    else:
        return 'balanced'

def analyze_emotion_level(text):
    """Analyze emotional expression level"""
    emotion_words = ['feel', 'felt', 'amazing', 'terrible', 'excited', 'sad', 'happy', 'frustrated']
    emotion_count = sum(1 for word in emotion_words if word in text.lower())

    if emotion_count > 3:
        return 'emotionally expressive'
    elif emotion_count > 1:
        return 'moderately emotional'
    else:
        return 'reserved'

def analyze_complexity(text):
    """Analyze language complexity"""
    words = text.split()
    avg_word_length = sum(len(word) for word in words) / len(words) if words else 0

    if avg_word_length > 5:
        return 'complex vocabulary'
    else:
        return 'simple vocabulary'

def extract_user_content_from_conversation(conversation_history, final_message):
    """
    Extract and format all user content from the conversation
    """
    user_messages = [msg.get('content', '') for msg in conversation_history if msg.get('role') == 'user']
    user_messages.append(final_message)

    return '\n\n'.join(user_messages)

def format_conversation_for_analysis(conversation_history):
    """
    Format conversation for LLM analysis
    """
    formatted = []
    for msg in conversation_history:
        role = "User" if msg.get('role') == 'user' else "Assistant"
        content = msg.get('content', '')
        formatted.append(f"{role}: {content}")

    return '\n'.join(formatted)

def summarize_conversation(conversation_history):
    """
    Create a summary of the conversation so far
    """
    if not conversation_history:
        return "This is the start of our conversation."

    user_messages = [msg.get('content', '') for msg in conversation_history if msg.get('role') == 'user']
    ai_messages = [msg.get('content', '') for msg in conversation_history if msg.get('role') == 'assistant']

    return f"We've exchanged {len(conversation_history)} messages. The user has shared: {' | '.join(user_messages[-2:])}"

def generate_conversation_suggestions(conversation_context):
    """
    Generate contextual suggestions for the user
    """

    # This could also use AI, but for now, simple contextual suggestions
    suggestions = []

    current_message = conversation_context['current_message'].lower()

    if 'work' in current_message:
        suggestions.extend([
            "How did that make me feel?",
            "What did I learn from this?",
            "What would I do differently?"
        ])
    elif 'friend' in current_message or 'family' in current_message:
        suggestions.extend([
            "What made that moment special?",
            "How has this relationship grown?",
            "What am I grateful for about them?"
        ])
    else:
        suggestions.extend([
            "What surprised me about today?",
            "How am I feeling right now?",
            "What do I want to remember about this?"
        ])

    return suggestions[:3]  # Return top 3 suggestions

def _get_publishing_recommendations(analysis):
    """Get publishing recommendations based on analysis"""
    recommendations = []
    score = analysis['publishability_score']

    if score >= 80:
        recommendations.append({
            'type': 'success',
            'message': 'Your journal is ready for publishing! High quality content with good structure.',
            'action': 'Proceed with publishing'
        })
    elif score >= 60:
        recommendations.append({
            'type': 'info',
            'message': 'Good foundation for publishing. Consider a few improvements for better market appeal.',
            'action': 'Review suggestions below'
        })
    else:
        recommendations.append({
            'type': 'warning',
            'message': 'Your journal needs some improvements before publishing for best results.',
            'action': 'Address the issues below'
        })

    # Specific recommendations
    if analysis['total_entries'] < 10:
        recommendations.append({
            'type': 'suggestion',
            'message': f'Add more entries. You have {analysis["total_entries"]}, but 10+ entries create better value for readers.',
            'action': 'Write more entries'
        })

    if analysis['avg_length'] < 75:
        recommendations.append({
            'type': 'suggestion',
            'message': f'Your average entry length is {int(analysis["avg_length"])} words. Longer entries (100+ words) provide more value.',
            'action': 'Expand shorter entries'
        })

    if len(analysis['themes']) < 3:
        recommendations.append({
            'type': 'suggestion',
            'message': 'Add more diverse themes and tags to your entries for broader appeal.',
            'action': 'Add tags and themes'
        })

    if analysis['quality_indicators']['has_tags'] < 50:
        recommendations.append({
            'type': 'suggestion',
            'message': 'Add tags to more entries to help with discoverability and organization.',
            'action': 'Tag your entries'
        })

    return recommendations

# Enhanced AIService class with additional methods
class AIService:
    # ... your existing methods ...

    @staticmethod
    def generate_conversational_response(prompt):
        """
        Generate a conversational response using your existing AI helpers
        """
        try:
            # Use your existing generate_ai_content function
            from ..utils.ai_helpers import generate_ai_content

            # Call your existing AI function - it should return a dict with 'entry' key
            response_data = generate_ai_content(prompt)

            # Extract the text content
            if isinstance(response_data, dict):
                return response_data.get('entry', response_data.get('content', str(response_data)))
            else:
                return str(response_data)

        except Exception as e:
            logger.error(f"Error generating conversational response: {e}")
            return "I'd love to hear more about that. What stood out to you most?"

    @staticmethod
    def generate_simple_response(prompt):
        """
        Generate a simple response for decision making
        """
        try:
            # Use your existing generate_ai_content function for simple decisions
            from ..utils.ai_helpers import generate_ai_content

            response_data = generate_ai_content(prompt)

            # Extract the text content
            if isinstance(response_data, dict):
                return response_data.get('entry', response_data.get('content', str(response_data)))
            else:
                return str(response_data)

        except Exception as e:
            logger.error(f"Error generating simple response: {e}")
            return "CONTINUE_CHAT - need more information"

    @staticmethod
    def generate_chat_decision(conversation_history, current_message):
        """
        Determine if we should create journal entry or continue chatting
        """
        user_messages = [msg for msg in conversation_history if msg.get('role') == 'user']

        # Simple heuristics first
        if len(user_messages) < 2:
            return False, "Need more conversation"

        if len(user_messages) >= 4:
            return True, "Sufficient content for journal entry"

        # For 2-3 messages, make a smarter decision based on content depth
        total_content_length = sum(len(msg.get('content', '')) for msg in user_messages)

        if total_content_length > 300:  # If they've shared substantial content
            return True, "Rich content provided"
        else:
            return False, "Could use more detail"

    @staticmethod
    def generate_marketing_copy(journal):
        """Generate marketing copy for a journal"""
        try:
            prompt = f"""
            Create marketing copy for this journal:
            Title: {journal.title}
            Description: {journal.description}
            Type: {journal.journal_type}

            Generate:
            1. A compelling tagline (10-15 words)
            2. A short description for marketplace (50-80 words)
            3. A social media post (with hashtags)
            4. An email subject line

            Make it engaging and authentic.
            """

            # Use your existing AI content generation
            from ..utils.ai_helpers import generate_ai_content
            response = generate_ai_content(prompt)

            return {
                'marketing_copy': response.get('entry', str(response)),
                'success': True
            }

        except Exception as e:
            logger.error(f"Error generating marketing copy: {e}")
            # Fallback marketing copy
            return {
                'marketing_copy': {
                    'tagline': f'Discover the transformative power of {journal.journal_type}',
                    'short_description': journal.description[:80] + '...' if len(journal.description) > 80 else journal.description,
                    'social_media': f'📖 New journal: "{journal.title}" - A personal journey of {journal.journal_type} and discovery. #journaling #{journal.journal_type}',
                    'email_subject': f'New Release: {journal.title}'
                },
                'success': True
            }



@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def request_nonce(request):
    """Generate and return a nonce for wallet authentication"""
    
    serializer = NonceRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    wallet_address = serializer.validated_data['wallet_address']
    
    try:
        # Generate nonce
        nonce = Web3Utils.generate_nonce()
        
        # Create expiry time
        expires_at = timezone.now() + timedelta(
            seconds=settings.WEB3_SETTINGS['NONCE_EXPIRY']
        )
        
        # Store nonce in database
        Web3Nonce.objects.create(
            wallet_address=wallet_address,
            nonce=nonce,
            expires_at=expires_at
        )
        
        # Create message for signing
        message = Web3Utils.create_auth_message(wallet_address, nonce)
        
        return Response({
            'nonce': nonce,
            'message': message,
            'expires_at': expires_at.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Nonce generation failed: {e}")
        return Response(
            {'error': 'Failed to generate nonce'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def web3_login(request):
    """Authenticate user with Web3 signature"""
    
    serializer = Web3LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    wallet_address = serializer.validated_data['wallet_address']
    signature = serializer.validated_data['signature']
    nonce = serializer.validated_data['nonce']
    wallet_type = serializer.validated_data.get('wallet_type', 'unknown')
    chain_id = serializer.validated_data.get('chain_id', 8453)
    
    try:
        # Verify nonce exists and is valid
        nonce_obj = Web3Nonce.objects.filter(
            wallet_address=wallet_address,
            nonce=nonce,
            is_used=False
        ).first()
        
        if not nonce_obj:
            return Response(
                {'error': 'Invalid or expired nonce'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if nonce_obj.is_expired():
            return Response(
                {'error': 'Nonce has expired'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify chain ID
        if not Web3Utils.is_valid_chain_id(chain_id):
            return Response(
                {'error': 'Unsupported blockchain network'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create and verify signature
        message = Web3Utils.create_auth_message(wallet_address, nonce)
        
        if not Web3Utils.verify_signature(message, signature, wallet_address):
            return Response(
                {'error': 'Invalid signature'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Mark nonce as used
        nonce_obj.is_used = True
        nonce_obj.save()
        
        # Get or create user
        user, created = User.objects.get_or_create(
            wallet_address=wallet_address,
            defaults={
                'username': f'user_{wallet_address[-8:]}',
                'wallet_type': wallet_type,
                'is_web3_verified': True,
                'preferred_chain_id': chain_id,
                'last_wallet_login': timezone.now()
            }
        )
        
        if not created:
            # Update existing user
            user.last_wallet_login = timezone.now()
            user.wallet_type = wallet_type
            user.preferred_chain_id = chain_id
            user.is_web3_verified = True
            user.save()
        
        # Create or get auth token
        token, _ = Token.objects.get_or_create(user=user)
        
        # Create wallet session
        session = WalletSession.objects.create(
            user=user,
            wallet_address=wallet_address,
            chain_id=chain_id,
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # Login user to Django session
        login(request, user)
        
        return Response({
            'token': token.key,
            'user': UserProfileSerializer(user).data,
            'session_id': str(session.session_id),
            'message': 'Successfully authenticated with Web3'
        })
        
    except Exception as e:
        logger.error(f"Web3 login failed: {e}")
        return Response(
            {'error': 'Authentication failed'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def disconnect_wallet(request):
    """Disconnect wallet and invalidate session"""
    
    try:
        # Deactivate wallet sessions
        WalletSession.objects.filter(
            user=request.user, 
            is_active=True
        ).update(is_active=False)
        
        # Delete auth token
        Token.objects.filter(user=request.user).delete()
        
        return Response({'message': 'Wallet disconnected successfully'})
        
    except Exception as e:
        logger.error(f"Wallet disconnection failed: {e}")
        return Response(
            {'error': 'Failed to disconnect wallet'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def user_profile(request):
    """Get current user's profile"""
    
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data)


@api_view(['PATCH'])
def update_profile(request):
    """Update user profile settings"""
    
    serializer = UserProfileSerializer(
        request.user, 
        data=request.data, 
        partial=True
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def anonymous_entry_preview(request, entry_uuid):
    """Preview page for anonymous entries stored in session"""
    
    # Convert UUID to string for comparison
    entry_uuid_str = str(entry_uuid)
    
    # Get anonymous entries from session
    anonymous_entries = request.session.get('anonymous_entries', [])
    
    # Find the specific entry
    entry_data = None
    for entry in anonymous_entries:
        if entry.get('id') == entry_uuid_str:
            entry_data = entry
            break
    
    if not entry_data:
        # Entry not found in session
        messages.warning(request, "Entry not found. It may have expired or you may need to log in.")
        return redirect('home')
    
    # Check if user is authenticated
    if request.user.is_authenticated:
        # User is now logged in - offer to save permanently
        messages.info(request, "You're now logged in! You can save this entry permanently.")
        
        # Prepare context for authenticated user
        context = {
            'entry': entry_data,
            'is_preview': True,
            'is_authenticated': True,
            'can_save_permanently': True,
            'wallet_info': {
                'address': entry_data.get('wallet_address'),
                'is_connected': bool(entry_data.get('wallet_address'))
            }
        }
    else:
        # User is still anonymous
        context = {
            'entry': entry_data,
            'is_preview': True,
            'is_authenticated': False,
            'can_save_permanently': False,
            'wallet_info': {
                'address': entry_data.get('wallet_address'),
                'is_connected': bool(entry_data.get('wallet_address'))
            }
        }
    
    # Use a simplified template or modify dashboard
    return render(request, 'diary/anonymous_entry_preview.html', context)