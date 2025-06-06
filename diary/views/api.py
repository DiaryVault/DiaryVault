import json
import logging
import time
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.shortcuts import get_object_or_404

from ..models import Entry, Tag
from ..utils.ai_helpers import generate_ai_content, generate_ai_content_personalized
from ..utils.analytics import get_content_hash, auto_generate_tags
from ..services.ai_service import AIService

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
    """Save a generated journal entry to the database"""
    try:
        # Check content type to determine how to process the request
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle multipart form data (with file uploads)
            title = request.POST.get('title')
            content = request.POST.get('content')
            mood = request.POST.get('mood')
            tags_json = request.POST.get('tags', '[]')
            photo = request.FILES.get('photo')

            # Parse tags from JSON string
            try:
                tags = json.loads(tags_json)
            except json.JSONDecodeError:
                tags = []

            # Store in session
            pending_entry = {
                'title': title,
                'content': content,
                'mood': mood,
                'tags': tags
            }
            # We can't store file objects in session, so just note if there was a photo
            if photo:
                pending_entry['had_photo'] = True
        else:
            # Handle JSON data (old method)
            data = json.loads(request.body)
            title = data.get('title')
            content = data.get('content')
            mood = data.get('mood')
            tags = data.get('tags', [])
            photo = None

            # Store in session
            pending_entry = {
                'title': title,
                'content': content,
                'mood': mood,
                'tags': tags
            }

        # Store in session regardless of authentication status
        request.session['pending_entry'] = pending_entry

        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'login_required': True,
                'message': 'Please log in to save your entry'
            }, status=401)

        # User is authenticated, proceed with saving
        if not title or not content:
            return JsonResponse({'success': False, 'error': 'Missing title or content'}, status=400)

        # Create the new entry
        entry = Entry.objects.create(
            user=request.user,
            title=title,
            content=content,
            mood=mood
        )

        # Save the photo if provided
        if photo:
            from ..models import EntryPhoto
            entry_photo = EntryPhoto.objects.create(
                entry=entry,
                photo=photo,
                caption="Journal photo"
            )

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

        # Clear the pending entry from session
        if 'pending_entry' in request.session:
            del request.session['pending_entry']

        return JsonResponse({
            'success': True,
            'entry_id': entry.id,
            'message': 'Entry saved successfully'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error saving generated entry: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Server error while saving entry',
            'details': str(e)
        }, status=500)

@require_POST
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
            photo = request.FILES.get('photo')
        else:
            data = json.loads(request.body)
            user_message = data.get('message', '')
            conversation_history = data.get('conversation_history', [])
            chat_mode = data.get('chat_mode', 'free-form')
            photo = None

        if not user_message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        # Parse conversation history if it's a string
        if isinstance(conversation_history, str):
            try:
                conversation_history = json.loads(conversation_history)
            except json.JSONDecodeError:
                conversation_history = []

        # Generate AI response based on conversation context
        ai_response_data = generate_chat_response(
            user_message=user_message,
            conversation_history=conversation_history,
            chat_mode=chat_mode,
            user=request.user if request.user.is_authenticated else None,
            photo=photo
        )

        # Add metadata
        ai_response_data['request_time'] = round(time.time() - start_time, 2)
        ai_response_data['request_id'] = request_id

        logger.info(f"Chat request {request_id} completed in {ai_response_data['request_time']}s")
        return JsonResponse(ai_response_data)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Chat request {request_id} failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Server error processing your request',
            'error_details': str(e),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, status=500)

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


# Add this to your existing AIService class in services/ai_service.py

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
