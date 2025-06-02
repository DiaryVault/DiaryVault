import time
import json
import logging
import re
from datetime import datetime, timedelta

import requests
from requests.exceptions import Timeout, ConnectionError, RequestException
from django.utils import timezone
from django.conf import settings
from django.apps import apps

from .decorators import retry_on_failure

logger = logging.getLogger(__name__)

def extract_json_from_text(text):
    """Extract JSON from text that might contain backticks and explanatory text"""
    # Look for JSON between triple backticks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        return json_match.group(1).strip()

    # If no backticks, try to find JSON by looking for opening brace
    try:
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            return text[json_start:json_end]
    except:
        pass

    # If all else fails, return the original text
    return text

@retry_on_failure(max_retries=3, delay=1, backoff=2)
def call_grok_api(journal_content, timeout=10):
    """
    Call the Grok API with retries, timeouts and better error handling
    """
    request_id = int(time.time() * 1000)  # Simple request ID for tracking
    logger.info(f"API Request {request_id} started for content of length {len(journal_content)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.GROK_API_KEY}',
            'X-Request-ID': str(request_id)  # Add request ID for tracking
        }

        today = datetime.now().strftime("%B %d, %Y")  # Get current date
        prompt = f"""
        Transform the following daily activities into a reflective, well-written journal entry.
        Add emotional depth, insights, and reflection while staying true to the events mentioned.

        Today's date: {today}  # Include today's date explicitly

        User's activities: {journal_content}

        Write the entry in first person as if the user wrote it themselves, with a thoughtful, introspective tone.
        Include paragraphs for readability and natural flow.
        """

        payload = {
            'model': 'llama-3.3-70b-versatile',
            'messages': [
                {'role': 'system', 'content': 'You are a helpful journal assistant that transforms brief notes into thoughtful diary entries.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 800
        }

        # Add proper timeout to prevent hanging requests
        start_time = time.time()
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=timeout  # Add timeout
        )
        api_time = time.time() - start_time

        # Log response time for performance monitoring
        logger.info(f"API Request {request_id} completed in {api_time:.2f}s with status {response.status_code}")

        if response.status_code != 200:
            logger.error(f"API Request {request_id} failed: {response.status_code} - {response.text}")
            raise RequestException(f"API returned status code {response.status_code}: {response.text}")

        response_data = response.json()

        # Validate response structure
        if 'choices' not in response_data or not response_data['choices']:
            error_msg = f"Invalid API response structure: {response_data}"
            logger.error(f"API Request {request_id}: {error_msg}")
            raise ValueError(error_msg)

        # Extract the message content based on the API response structure
        return response_data['choices'][0]['message']['content']

    except Timeout:
        logger.error(f"API Request {request_id} timed out after {timeout}s")
        raise Timeout(f"Request timed out after {timeout} seconds")
    except ConnectionError as e:
        logger.error(f"API Request {request_id} connection error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"API Request {request_id} unexpected error: {str(e)}", exc_info=True)
        raise

@retry_on_failure(max_retries=2, delay=1, backoff=2)
def generate_title(journal_entry, timeout=5):
    """
    Generate a title for the journal entry with improved error handling
    """
    request_id = int(time.time() * 1000)
    logger.info(f"Title generation {request_id} started for entry of length {len(journal_entry)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.GROK_API_KEY}',
            'X-Request-ID': str(request_id)
        }

        prompt = f"""
        Create a short, engaging title for this journal entry:

        {journal_entry[:300]}...

        The title should be 5-7 words maximum, reflecting the main themes or feelings in the entry.
        """

        payload = {
            'model': 'llama-3.3-70b-versatile',
            'messages': [
                {'role': 'system', 'content': 'You are a helpful writing assistant.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 30
        }

        start_time = time.time()
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=timeout
        )
        api_time = time.time() - start_time

        logger.info(f"Title generation {request_id} completed in {api_time:.2f}s with status {response.status_code}")

        if response.status_code != 200:
            logger.error(f"Title generation {request_id} failed: {response.status_code} - {response.text}")
            raise RequestException(f"API returned status code {response.status_code}")

        response_data = response.json()

        # Validate response structure with detailed error
        if 'choices' not in response_data:
            error_msg = f"Missing 'choices' in API response: {response_data}"
            logger.error(f"Title generation {request_id}: {error_msg}")
            raise ValueError(error_msg)

        if not response_data['choices'] or 'message' not in response_data['choices'][0]:
            error_msg = f"Invalid structure in API response: {response_data}"
            logger.error(f"Title generation {request_id}: {error_msg}")
            raise ValueError(error_msg)

        title = response_data['choices'][0]['message']['content'].strip('"').strip()

        # Add today's date to the title
        today = datetime.now().strftime("%B %d, %Y")
        return f"{title} - {today}"

    except Exception as e:
        logger.error(f"Title generation {request_id} error: {str(e)}", exc_info=True)
        # More descriptive fallback title
        today = datetime.now().strftime("%B %d, %Y")
        words = journal_entry.split()[:5]
        if words:
            # Create a title from the first few words
            return f"{' '.join(words)}... - {today}"
        return f"Journal Entry - {today}"

def generate_ai_content(journal_content):
    """
    Generate both journal entry and title with comprehensive error handling
    """
    try:
        # Start tracking performance
        start_time = time.time()

        # Generate the journal entry
        journal_entry = call_grok_api(journal_content)
        journal_time = time.time() - start_time

        # Then generate a title based on the entry
        title_start = time.time()
        title = generate_title(journal_entry)
        title_time = time.time() - title_start

        total_time = time.time() - start_time

        # Log performance metrics
        logger.info(f"Content generation completed - Entry: {journal_time:.2f}s, Title: {title_time:.2f}s, Total: {total_time:.2f}s")

        return {
            'title': title,
            'entry': journal_entry,
            'generation_time': round(total_time, 2)
        }
    except Exception as e:
        logger.error(f"Error in generate_ai_content: {str(e)}", exc_info=True)
        # Return fallback content
        today = datetime.now().strftime("%B %d, %Y")
        return {
            'title': f"Journal Entry - {today}",
            'entry': f"Today I {journal_content[:50]}..." if len(journal_content) > 50 else f"Today I {journal_content}...",
            'error': str(e)
        }

def get_user_preferences(user):
    """Get user preferences or return defaults for anonymous users"""
    if not user or not user.is_authenticated:
        return {
            'writing_style': 'reflective',
            'tone': 'balanced',
            'focus_areas': [],
            'language_complexity': 'moderate',
            'include_questions': True,
            'metaphor_frequency': 'occasional'
        }

    try:
        UserPreference = apps.get_model('diary', 'UserPreference')
        prefs = UserPreference.objects.get(user=user)

        # Check if get_focus_areas_list method exists
        if hasattr(prefs, 'get_focus_areas_list'):
            focus_areas = prefs.get_focus_areas_list()
        else:
            # Fallback if method doesn't exist
            focus_areas = []
            if hasattr(prefs, 'focus_areas') and prefs.focus_areas:
                focus_areas = [area.strip() for area in prefs.focus_areas.split(',') if area.strip()]

        return {
            'writing_style': prefs.writing_style,
            'tone': prefs.tone,
            'focus_areas': focus_areas,
            'language_complexity': prefs.language_complexity,
            'include_questions': prefs.include_questions,
            'metaphor_frequency': prefs.metaphor_frequency
        }
    except Exception as e:
        logger.error(f"Error getting user preferences: {str(e)}", exc_info=True)
        # Return defaults if UserPreference model doesn't exist or there's an error
        return {
            'writing_style': 'reflective',
            'tone': 'balanced',
            'focus_areas': [],
            'language_complexity': 'moderate',
            'include_questions': True,
            'metaphor_frequency': 'occasional'
        }

@retry_on_failure(max_retries=3, delay=1, backoff=2)
def call_grok_api_personalized(journal_content, user_preferences):
    """
    Call the Grok API with personalized parameters based on user preferences
    """
    request_id = int(time.time() * 1000)
    logger.info(f"Personalized API Request {request_id} started for content length {len(journal_content)}")

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.GROK_API_KEY}',
            'X-Request-ID': str(request_id)
        }

        # Build a personalized prompt based on preferences
        style_guide = ""

        # Writing style
        if user_preferences['writing_style'] == 'reflective':
            style_guide += "Write in a thoughtful, introspective tone with personal insights. "
        elif user_preferences['writing_style'] == 'analytical':
            style_guide += "Write in a logical, analytical tone with observations about patterns and causes. "
        elif user_preferences['writing_style'] == 'creative':
            style_guide += "Write in a creative, expressive tone with vivid descriptions and imagery. "
        elif user_preferences['writing_style'] == 'concise':
            style_guide += "Write concisely and to the point, focusing on key events and feelings. "
        elif user_preferences['writing_style'] == 'detailed':
            style_guide += "Include rich details and thorough descriptions of events, feelings, and surroundings. "
        elif user_preferences['writing_style'] == 'poetic':
            style_guide += "Include poetic language, metaphors, and a flowing, rhythmic writing style. "
        elif user_preferences['writing_style'] == 'humorous':
            style_guide += "Incorporate gentle humor and a lighthearted tone where appropriate. "

        # Emotional tone
        if user_preferences['tone'] == 'positive':
            style_guide += "Emphasize positive aspects and silver linings in events. "
        elif user_preferences['tone'] == 'balanced':
            style_guide += "Balance both positive and challenging aspects of experiences. "
        elif user_preferences['tone'] == 'realistic':
            style_guide += "Take a realistic, pragmatic approach to describing events. "
        elif user_preferences['tone'] == 'growth':
            style_guide += "Focus on lessons learned and personal growth opportunities. "

        # Focus areas
        if user_preferences['focus_areas']:
            areas = ', '.join(user_preferences['focus_areas'])
            style_guide += f"When relevant, emphasize these areas: {areas}. "

        # Language complexity
        if user_preferences['language_complexity'] == 'simple':
            style_guide += "Use simple, clear language avoiding complex vocabulary. "
        elif user_preferences['language_complexity'] == 'moderate':
            style_guide += "Use moderately sophisticated language accessible to most readers. "
        elif user_preferences['language_complexity'] == 'advanced':
            style_guide += "Use rich, sophisticated vocabulary and complex sentence structures. "

        # Metaphor frequency
        if user_preferences['metaphor_frequency'] == 'minimal':
            style_guide += "Use metaphors and analogies sparingly. "
        elif user_preferences['metaphor_frequency'] == 'occasional':
            style_guide += "Occasionally include metaphors or analogies to illustrate points. "
        elif user_preferences['metaphor_frequency'] == 'frequent':
            style_guide += "Frequently incorporate metaphors and analogies throughout the entry. "

        # Questions
        if user_preferences['include_questions']:
            style_guide += "End with 1-2 thoughtful reflective questions related to the events. "

        # Build the prompt with style guide
        today = datetime.now().strftime("%B %d, %Y")
        prompt = f"""
        Transform the following daily activities into a reflective, well-written journal entry.
        Add emotional depth, insights, and reflection while staying true to the events mentioned.

        User's activities: {journal_content}

        Style guide: {style_guide}

        Write the entry in first person as if the user wrote it themselves.
        Include paragraphs for readability and natural flow.
        """

        payload = {
            'model': 'llama-3.3-70b-versatile',
            'messages': [
                {'role': 'system', 'content': 'You are a helpful journal assistant that transforms brief notes into thoughtful diary entries.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 800
        }

        # Add proper timeout to prevent hanging requests
        start_time = time.time()
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=10
        )
        api_time = time.time() - start_time

        logger.info(f"API Request {request_id} completed in {api_time:.2f}s with status {response.status_code}")

        if response.status_code != 200:
            logger.error(f"API Request {request_id} failed: {response.status_code} - {response.text}")
            raise RequestException(f"API returned status code {response.status_code}")

        response_data = response.json()

        # Validate response structure
        if 'choices' not in response_data or not response_data['choices']:
            error_msg = f"Invalid API response structure: {response_data}"
            logger.error(f"API Request {request_id}: {error_msg}")
            raise ValueError(error_msg)

        return response_data['choices'][0]['message']['content']

    except Exception as e:
        logger.error(f"API Request {request_id} error: {str(e)}", exc_info=True)
        raise

def generate_ai_content_personalized(journal_content, user=None):
    """
    Generate both journal entry and title with personalization
    """
    try:
        # Get user preferences
        preferences = get_user_preferences(user)

        # Start tracking performance
        start_time = time.time()

        # Generate the journal entry with personalization
        journal_entry = call_grok_api_personalized(journal_content, preferences)
        journal_time = time.time() - start_time

        # Then generate a title based on the entry
        title_start = time.time()
        title = generate_title(journal_entry)
        title_time = time.time() - title_start

        total_time = time.time() - start_time

        # Log performance metrics
        logger.info(f"Personalized content generation completed - Entry: {journal_time:.2f}s, Title: {title_time:.2f}s, Total: {total_time:.2f}s")

        return {
            'title': title,
            'entry': journal_entry,
            'generation_time': round(total_time, 2),
            'personalized': True,
            'preferences_used': preferences
        }
    except Exception as e:
        logger.error(f"Error in personalized content generation: {str(e)}", exc_info=True)
        # Fallback to non-personalized version
        try:
            return generate_ai_content(journal_content)
        except Exception as inner_e:
            logger.error(f"Fallback content generation also failed: {str(inner_e)}", exc_info=True)
            # Final fallback
            today = datetime.now().strftime("%B %d, %Y")
            return {
                'title': f"Journal Entry - {today}",
                'entry': f"Today I {journal_content[:50]}..." if len(journal_content) > 50 else f"Today I {journal_content}...",
                'error': str(e),
                'personalized': False
            }
