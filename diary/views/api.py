# Core Python
import json
import logging
import time
import uuid
from datetime import datetime

# Django core
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.backends import ModelBackend
from django.core.cache import cache
from django.db.models import Count, Avg
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Django REST framework
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

# Local app imports
from .. import models
from ..models import Entry, Journal, Tag, JournalEntry
from ..serializers import NonceRequestSerializer, Web3LoginSerializer, UserProfileSerializer
from ..services.ai_service import AIService
from ..utils.ai_helpers import generate_ai_content, generate_ai_content_personalized
from ..utils.analytics import get_content_hash, auto_generate_tags
from diary.models import Web3Nonce, WalletSession
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
            photo = request.FILES.get('journal_photo')
            
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

        # Format wallet address if provided
        if wallet_address:
            wallet_address = Web3Utils.format_wallet_address(wallet_address)

        # Check if user has wallet but isn't authenticated
        if not request.user.is_authenticated and wallet_address:
            # Try to authenticate the user with their wallet address
            try:
                # Get user by wallet address
                user = User.objects.filter(wallet_address=wallet_address).first()
                
                if user:
                    # User exists, log them in
                    login(request, user)
                    logger.info(f"Auto-authenticated user {user.id} with wallet {wallet_address}")
                else:
                    # Create new user with wallet
                    user = User.objects.create(
                        wallet_address=wallet_address,
                        username=f'user_{wallet_address[-8:]}',
                        is_web3_verified=True,
                        preferred_chain_id=int(chain_id) if chain_id else 8453,
                        last_wallet_login=timezone.now(),
                        is_active=True
                    )
                    
                    # Create user preferences
                    from ..models import UserPreference
                    UserPreference.objects.get_or_create(user=user)
                    
                    # Create auth token
                    Token.objects.get_or_create(user=user)
                    
                    # Create wallet session
                    WalletSession.objects.create(
                        user=user,
                        wallet_address=wallet_address,
                        chain_id=int(chain_id) if chain_id else 8453,
                        ip_address=request.META.get('REMOTE_ADDR', ''),
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Log the user in
                    login(request, user)
                    logger.info(f"Created and authenticated new user {user.id} with wallet {wallet_address}")
                
                # Update session
                request.session['wallet_address'] = wallet_address
                request.session['chain_id'] = chain_id
                request.session['wallet_connected'] = True
                request.session.modified = True
                
            except Exception as e:
                logger.error(f"Error auto-authenticating wallet user: {e}")
                # Continue without authentication if there's an error

        # Now check if user is authenticated (either was already or just got authenticated)
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
                try:
                    from ..utils.analytics import auto_generate_tags
                    tags = auto_generate_tags(content, mood)
                except ImportError:
                    logger.warning("auto_generate_tags not found, skipping tag generation")
                    tags = []

            if tags:
                for tag_name in tags:
                    if tag_name and isinstance(tag_name, str):
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
            
            # Clear anonymous entries if user just got authenticated
            if 'anonymous_entries' in request.session:
                del request.session['anonymous_entries']

            # Set entry_saved flag in session for dashboard
            request.session['entry_saved'] = True
            request.session.modified = True

            # Redirect to dashboard
            return JsonResponse({
                'success': True,
                'entry_id': entry.id,
                'rewards': total_rewards,
                'redirect_url': '/dashboard/?entry_saved=true',
                'message': 'Entry saved successfully!',
                'is_authenticated': True,
                'wallet_connected': bool(wallet_address)
            })
        else:
            # For anonymous users (no wallet connected), save to session
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
            
            # Initialize anonymous_entries as dict if not exists
            if 'anonymous_entries' not in request.session:
                request.session['anonymous_entries'] = {}
            
            # Handle existing data that might be in list format
            existing_entries = request.session.get('anonymous_entries', {})
            
            if isinstance(existing_entries, list):
                # Convert list to dict
                new_entries = {}
                for idx, entry in enumerate(existing_entries):
                    entry_id = entry.get('id', str(uuid.uuid4()))
                    new_entries[entry_id] = entry
                request.session['anonymous_entries'] = new_entries
                existing_entries = new_entries
            
            # Add the new entry
            request.session['anonymous_entries'][temp_id] = session_entry
            request.session['pending_entry'] = session_entry
            request.session.modified = True
            
            # Calculate mock rewards
            word_count = len(content.split())
            base_reward = word_count // 10
            wallet_bonus = 5 if wallet_address else 0
            total_rewards = base_reward + wallet_bonus
            
            # Return response for anonymous users
            return JsonResponse({
                'success': True,
                'entry_id': temp_id,
                'rewards': total_rewards,
                'is_anonymous': True,
                'message': 'Entry saved temporarily. Connect your wallet to save permanently and earn real rewards!',
                'redirect_url': None,  # Don't redirect for anonymous users
                'auth_required': True,
                'login_url': '/login/?save_after_login=true&next=/dashboard/',
                'signup_url': '/signup/?feature=journal&next=/dashboard/',
                'wallet_connect_prompt': True
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
    """Redirect anonymous entries to journal form with pre-filled content"""
    
    # Convert UUID to string
    entry_uuid_str = str(entry_uuid)
    
    # Get anonymous entries from session
    anonymous_entries = request.session.get('anonymous_entries', {})
    
    if entry_uuid_str in anonymous_entries:
        # User is logged in - redirect to journal with the entry data
        if request.user.is_authenticated:
            return redirect(f'/journal/?pending_entry={entry_uuid_str}')
        else:
            # User is not logged in - show a message and redirect to signup
            messages.info(
                request, 
                'Please sign up or log in to save your journal entry permanently.'
            )
            # Store the entry ID in session for after login
            request.session['pending_entry_after_login'] = entry_uuid_str
            return redirect(f'/signup/?feature=journal&next=/journal/?pending_entry={entry_uuid_str}')
    
    # Entry not found, redirect to journal
    messages.warning(request, "Entry not found. Please create a new journal entry.")
    return redirect('new_entry')

@csrf_exempt
@require_POST
def connect_wallet_session(request):
    """Store wallet connection in session for anonymous users (before full auth)"""
    try:
        data = json.loads(request.body)
        wallet_address = data.get('wallet_address')
        chain_id = data.get('chain_id', 8453)  # Default to Base
        
        if wallet_address:
            # Store in session for anonymous users
            request.session['wallet_address'] = wallet_address
            request.session['chain_id'] = chain_id
            request.session['wallet_connected'] = True
            request.session.modified = True
            
            # Check if user has pending entries
            pending_entries_count = len(request.session.get('anonymous_entries', {}))
            
            return JsonResponse({
                'success': True,
                'message': 'Wallet connected to session',
                'can_save_entries': True,
                'pending_entries': pending_entries_count,
                'next_step': 'web3_auth' if pending_entries_count > 0 else 'continue'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'No wallet address provided'
            })
            
    except Exception as e:
        logger.error(f"Error connecting wallet to session: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

def web3_complete_profile(request):
    """Bridge between anonymous wallet connection and full Web3 auth"""
    entry_id = request.GET.get('entry_id')
    
    if request.method == 'POST':
        # This is now a bridge to the full Web3 auth flow
        wallet_address = request.session.get('wallet_address')
        if not wallet_address:
            messages.error(request, 'No wallet connected. Please connect your wallet first.')
            return redirect('journal')
        
        # Redirect to the Web3 auth flow with the wallet already connected
        messages.info(request, 'Please complete authentication by signing with your wallet.')
        return redirect(f"{reverse('web3_login')}?entry_id={entry_id}")
    
    # GET request - show profile completion/auth prompt
    context = {
        'wallet_address': request.session.get('wallet_address'),
        'entry_id': entry_id,
        'anonymous_entries_count': len(request.session.get('anonymous_entries', {}))
    }
    
    # Try to render a simple template, or redirect if it doesn't exist
    try:
        return render(request, 'diary/web3_complete_profile.html', context)
    except:
        # If template doesn't exist, show a message and redirect
        messages.info(request, 'Please sign with your wallet to save your entries.')
        return redirect(f"/journal/?show_wallet_prompt=true&entry_id={entry_id}")

def anonymous_entry_preview(request, entry_uuid):
    """Handle preview of anonymous entries"""
    
    # Convert UUID to string
    entry_uuid_str = str(entry_uuid)
    
    # Get anonymous entries from session
    anonymous_entries = request.session.get('anonymous_entries', {})
    
    if entry_uuid_str in anonymous_entries:
        # User is logged in - transfer the entry
        if request.user.is_authenticated:
            entry_data = anonymous_entries[entry_uuid_str]
            
            try:
                # Create the entry for the logged-in user
                entry = Entry.objects.create(
                    user=request.user,
                    title=entry_data.get('title', 'Untitled'),
                    content=entry_data.get('content', ''),
                    mood=entry_data.get('mood', 'neutral')
                )
                
                # Add tags
                tags = entry_data.get('tags', [])
                for tag_name in tags:
                    if tag_name:
                        tag, created = Tag.objects.get_or_create(
                            name=tag_name.lower().strip(),
                            user=request.user
                        )
                        entry.tags.add(tag)
                
                # Remove from anonymous entries
                del anonymous_entries[entry_uuid_str]
                request.session['anonymous_entries'] = anonymous_entries
                request.session.modified = True
                
                messages.success(request, 'Entry saved to your account!')
                return redirect('entry_detail', entry_id=entry.id)
                
            except Exception as e:
                logger.error(f"Error transferring anonymous entry: {e}")
                messages.error(request, 'Error saving entry. Please try again.')
                return redirect('journal')
        else:
            # User is not logged in - prompt to sign up/login
            messages.info(
                request, 
                'Connect your wallet to save this entry permanently and earn rewards!'
            )
            # Store the entry ID for after login
            request.session['pending_entry_uuid'] = entry_uuid_str
            request.session.modified = True
            
            # Redirect to journal with wallet prompt
            return redirect(f"/journal/?show_wallet_prompt=true&entry_id={entry_uuid_str}")
    
    # Entry not found
    messages.warning(request, "Entry not found. Please create a new journal entry.")
    return redirect('new_entry')

@login_required
def save_entry_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from .models import Entry
        
        entry = Entry.objects.create(
            user=request.user,
            title=request.POST.get('title', 'Untitled Entry'),
            content=request.POST.get('content', ''),
            mood=request.POST.get('mood', ''),
        )
        
        # Handle photo if provided
        if 'photo' in request.FILES:
            from .models import EntryPhoto
            EntryPhoto.objects.create(
                entry=entry,
                photo=request.FILES['photo']
            )
        
        return JsonResponse({
            'success': True,
            'entry_id': entry.id,
            'message': 'Entry saved successfully'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
def user_stats(request):
    """Get current user statistics"""
    try:
        from django.db.models import Sum
        from django.utils import timezone
        from datetime import timedelta
        
        entries = Entry.objects.filter(user=request.user)
        
        # Total entries
        total_entries = entries.count()
        
        # Total words
        total_words = sum(len(entry.content.split()) for entry in entries)
        
        # Calculate streak
        today = timezone.now().date()
        entry_dates = list(entries.values_list('created_at__date', flat=True).distinct().order_by('-created_at__date'))
        
        streak = 0
        if entry_dates:
            if entry_dates[0] == today or entry_dates[0] == today - timedelta(days=1):
                streak = 1
                current_date = entry_dates[0]
                
                for entry_date in entry_dates[1:]:
                    expected_date = current_date - timedelta(days=1)
                    if entry_date == expected_date:
                        streak += 1
                        current_date = entry_date
                    else:
                        break
        
        # Get mood counts
        mood_counts = {}
        for entry in entries:
            if entry.mood:
                mood_counts[entry.mood] = mood_counts.get(entry.mood, 0) + 1
        
        # Get dominant mood
        dominant_mood = max(mood_counts.items(), key=lambda x: x[1])[0] if mood_counts else None
        
        return JsonResponse({
            'success': True,
            'total_entries': total_entries,
            'total_words': total_words,
            'streak': streak,
            'dominant_mood': dominant_mood,
            'mood_counts': mood_counts
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    
def recent_entries(request):
    """Return recent entries for dashboard updates"""
    entries = Entry.objects.filter(user=request.user).order_by('-created_at')[:6]
    
    entries_data = []
    for entry in entries:
        entry_data = {
            'id': entry.id,
            'title': entry.title or 'Untitled',
            'created_at': entry.created_at.strftime('%b %d, %Y'),
            'has_photo': bool(entry.photo or entry.photos.exists())
        }
        
        if entry.photos.exists():
            entry_data['photo_url'] = entry.photos.first().photo.url
        elif entry.photo:
            entry_data['photo_url'] = entry.photo.url
            
        entries_data.append(entry_data)
    
    return JsonResponse({'entries': entries_data})

@csrf_exempt
def connect_wallet_session(request):
    """Save wallet connection to session for anonymous users"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            wallet_address = data.get('wallet_address')
            chain_id = data.get('chain_id')
            
            if wallet_address:
                # Save to session
                request.session['wallet_address'] = wallet_address.lower()
                request.session['chain_id'] = chain_id
                request.session.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Wallet connected to session'
                })
            
            return JsonResponse({
                'success': False,
                'error': 'No wallet address provided'
            }, status=400)
            
        except Exception as e:
            logger.error(f"Error connecting wallet to session: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def wallet_connect_api(request):
    """API endpoint to handle wallet connection"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            wallet_address = data.get('address')
            chain_id = data.get('chainId')
            
            if wallet_address:
                # Store wallet connection in session
                request.session['wallet_connected'] = True
                request.session['wallet_address'] = wallet_address
                request.session['wallet_chain_id'] = chain_id
                request.session['wallet_connected_at'] = timezone.now().isoformat()
                
                # Get or create user based on wallet
                user, created = User.objects.get_or_create(
                    username=f'wallet_{wallet_address[:8]}',
                    defaults={
                        'email': f'{wallet_address[:8]}@diaryvault.local',
                        'is_wallet_user': True,
                    }
                )
                
                # Log the user in
                from django.contrib.auth import login
                login(request, user)
                
                return JsonResponse({
                    'success': True,
                    'wallet_address': wallet_address,
                    'user_created': created,
                    'redirect': reverse('dashboard')
                })
            
            return JsonResponse({'error': 'Invalid wallet address'}, status=400)
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def wallet_disconnect_api(request):
    """API endpoint to handle wallet disconnection"""
    if request.method == 'POST':
        # Clear wallet session data
        request.session.pop('wallet_connected', None)
        request.session.pop('wallet_address', None)
        request.session.pop('wallet_chain_id', None)
        request.session.pop('wallet_connected_at', None)
        
        # Log the user out
        from django.contrib.auth import logout
        logout(request)
        
        return JsonResponse({
            'success': True,
            'redirect': reverse('home')
        })
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)