import json
import logging
import time
import requests
from datetime import datetime, timedelta
from requests.exceptions import Timeout, ConnectionError, RequestException
from typing import List, Dict, Any, Optional
from django.contrib.auth.models import User

from django.utils import timezone
from django.conf import settings
from django.apps import apps

from ..utils.ai_helpers import generate_ai_content, generate_ai_content_personalized

logger = logging.getLogger(__name__)

class AIService:
    """
    Service class for AI integration features

    This class centralizes all AI-related functionality, making it easier to:
    1. Track and log AI usage
    2. Swap out AI providers if needed
    3. Implement rate limiting or quotas
    4. Cache common requests
    """

    @staticmethod
    def generate_entry_summary(entry):
        """Generate a summary for a diary entry"""
        try:
            # Store previous summary as a version if it exists
            if entry.summary:
                SummaryVersion = apps.get_model('diary', 'SummaryVersion')
                SummaryVersion.objects.create(
                    entry=entry,
                    summary=entry.summary
                )

            # Get response from Groq
            prompt = f"""
            Analyze this diary entry and provide a thoughtful summary with insights about the person's feelings,
            motivations, and patterns. Identify any notable themes or emotional states:

            Title: {entry.title}
            Date: {entry.created_at.strftime('%Y-%m-%d')}
            Content: {entry.content}

            Format your response as a brief summary (2-3 paragraphs) focused on psychological insights.
            """

            summary = AIService._get_groq_response(prompt)

            # Update the entry with new summary
            entry.summary = summary
            entry.summary_generated_at = timezone.now()
            entry.save()

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return "Unable to generate summary at this time."

    @staticmethod
    def extract_json_from_text(text):
        """Extract JSON from text that might contain backticks and explanatory text"""
        # Look for JSON between triple backticks
        import re
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

    @staticmethod
    def generate_insights(user, entries=None):
        """Generate insights based on user's diary entries"""
        try:
            Entry = apps.get_model('diary', 'Entry')
            UserInsight = apps.get_model('diary', 'UserInsight')

            if entries is None:
                entries = Entry.objects.filter(user=user).order_by('-created_at')[:20]

            if not entries:
                return []

            # Prepare entry data
            entry_data = "\n\n".join([
                f"Entry {i+1}:\nTitle: {entry.title}\nDate: {entry.created_at.strftime('%Y-%m-%d')}\nContent: {entry.content[:200]}..."
                for i, entry in enumerate(entries)
            ])

            prompt = f"""
            Based on these diary entries, identify patterns, make observations about mood trends,
            and suggest personal growth opportunities. Focus on:

            1. Recurring themes or concerns
            2. Mood patterns
            3. Potential areas for personal development
            4. Notable achievements or progress

            {entry_data}

            Format your response as JSON with the following structure:
            {{
                "patterns": [
                    {{"title": "Pattern title", "description": "Description of pattern"}}
                ],
                "suggestions": [
                    {{"title": "Suggestion title", "description": "Description of suggestion"}}
                ],
                "mood_analysis": {{"title": "Mood Analysis", "description": "Overall mood analysis"}}
            }}
            """

            response = AIService._get_groq_response(prompt)

            # Parse JSON response
            try:
                json_text = AIService.extract_json_from_text(response)
                insights_data = json.loads(json_text)

                # Clear previous insights
                UserInsight.objects.filter(user=user).delete()

                # Create new insights
                insights = []

                # Add patterns
                for pattern in insights_data.get('patterns', []):
                    insight = UserInsight.objects.create(
                        user=user,
                        title=pattern['title'],
                        content=pattern.get('description', ''),  # Handle both description and content keys
                        insight_type='pattern'
                    )
                    insights.append(insight)

                # Add suggestions
                for suggestion in insights_data.get('suggestions', []):
                    insight = UserInsight.objects.create(
                        user=user,
                        title=suggestion['title'],
                        content=suggestion.get('description', ''),  # Handle both description and content keys
                        insight_type='suggestion'
                    )
                    insights.append(insight)

                # Add mood analysis
                mood = insights_data.get('mood_analysis', {})
                if mood:
                    insight = UserInsight.objects.create(
                        user=user,
                        title=mood['title'],
                        content=mood.get('description', ''),  # Handle both description and content keys
                        insight_type='mood_analysis'  # Use consistent naming
                    )
                    insights.append(insight)

                return insights

            except json.JSONDecodeError:
                logger.error(f"Error parsing AI response as JSON: {response}")
                return []

        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            return []

    @staticmethod
    def generate_biography(user, time_period_start=None, time_period_end=None):
        """Generate a biography based on a user's diary entries"""
        try:
            Entry = apps.get_model('diary', 'Entry')
            Biography = apps.get_model('diary', 'Biography')

            # Get entries for the specified time period
            entries = Entry.objects.filter(user=user)
            if time_period_start:
                entries = entries.filter(created_at__date__gte=time_period_start)
            if time_period_end:
                entries = entries.filter(created_at__date__lte=time_period_end)

            entries = entries.order_by('created_at')

            if not entries:
                return None

            # Prepare entry data
            entry_data = "\n\n".join([
                f"Entry {i+1}:\nTitle: {entry.title}\nDate: {entry.created_at.strftime('%Y-%m-%d')}\nContent: {entry.content[:500]}..."
                for i, entry in enumerate(entries[:30])  # Limit to 30 entries to avoid token limits
            ])

            period_description = ""
            if time_period_start and time_period_end:
                period_description = f"from {time_period_start.strftime('%B %Y')} to {time_period_end.strftime('%B %Y')}"

            prompt = f"""
            Write a cohesive, first-person biography based on these diary entries {period_description}.
            Craft a narrative that captures the person's experiences, growth, and significant events.
            Use a personal, reflective tone as if the person is telling their own life story.

            {entry_data}

            Write the biography as a thoughtful, introspective personal narrative with natural transitions
            between events and themes. Use the first person perspective. Make it emotionally resonant and
            capture the person's voice based on their diary entries.

            The biography should be divided into clear paragraphs and should be around 500-800 words.
            """

            biography_content = AIService._get_groq_response(prompt)

            # Create or update biography
            biography, created = Biography.objects.update_or_create(
                user=user,
                time_period_start=time_period_start,
                time_period_end=time_period_end,
                defaults={
                    'content': biography_content,
                    'title': f"My Life Story {period_description}"
                }
            )

            return biography

        except Exception as e:
            logger.error(f"Error generating biography: {str(e)}")
            return None

    @staticmethod
    def generate_journal_entry(journal_content, user=None, personalize=False):
        """Generate a full journal entry from brief notes"""
        try:
            if personalize and user:
                return generate_ai_content_personalized(journal_content, user)
            else:
                return generate_ai_content(journal_content)
        except Exception as e:
            logger.error(f"Error generating journal entry: {str(e)}", exc_info=True)
            return {
                'error': f"Failed to generate journal entry: {str(e)}",
                'title': "Journal Entry",
                'entry': journal_content
            }

    @staticmethod
    def generate_user_biography(user, chapter=None):
        """
        Generate a biography for a user based on their journal entries
        Returns the generated biography text
        """
        # Import models using apps.get_model to avoid circular imports
        from django.apps import apps
        from django.utils import timezone
        import time
        import json
        import requests
        from django.conf import settings
        from requests.exceptions import RequestException
        import logging

        logger = logging.getLogger(__name__)

        Entry = apps.get_model('diary', 'Entry')
        UserInsight = apps.get_model('diary', 'UserInsight')
        Biography = apps.get_model('diary', 'Biography')

        # Try to get LifeChapter if it exists
        try:
            LifeChapter = apps.get_model('diary', 'LifeChapter')
            has_life_chapters = True
        except LookupError:
            has_life_chapters = False

        request_id = int(time.time() * 1000)
        logger.info(f"Biography generation {request_id} started for user {user.username}")

        try:
            # Get all entries for this user
            entries = Entry.objects.filter(user=user).order_by('-created_at')

            if not entries:
                logger.warning(f"No journal entries found for user {user.username}")
                return "Add more journal entries to generate your biography. Your life story will be crafted based on your journaling history."

            # Get entry content samples (limit to prevent token overflow)
            entry_samples = []
            for entry in entries[:20]:  # Use up to 20 most recent entries
                entry_sample = {
                    'date': entry.created_at.strftime('%Y-%m-%d'),
                    'title': entry.title,
                    'content': entry.content[:300] + "..." if len(entry.content) > 300 else entry.content,
                }

                # Add mood if it exists
                if hasattr(entry, 'mood') and entry.mood:
                    entry_sample['mood'] = entry.mood

                # Add tags if they exist
                if hasattr(entry, 'tags'):
                    try:
                        entry_sample['tags'] = ", ".join([tag.name for tag in entry.tags.all()])
                    except:
                        pass

                entry_samples.append(entry_sample)

            # Get user insights if available
            insights = UserInsight.objects.filter(user=user)
            insight_texts = [f"{insight.title}: {insight.content}" for insight in insights]

            # Format entries and insights as context for the API
            entries_text = json.dumps(entry_samples, indent=2)
            insights_text = "\n".join(insight_texts) if insight_texts else "No insights available yet."

            # Determine which chapter to generate
            chapter_content = ""
            if chapter and has_life_chapters:
                chapter_obj = None
                try:
                    chapter_obj = LifeChapter.objects.get(user=user, title__iexact=chapter) or \
                                LifeChapter.objects.get(user=user, slug__iexact=chapter)

                    chapter_title = chapter_obj.title
                    chapter_description = chapter_obj.description

                except LifeChapter.DoesNotExist:
                    # Use the provided chapter name directly
                    chapter_title = chapter
                    chapter_description = f"Events related to {chapter}"

                chapter_content = f"""
                Focus on generating content for the chapter: "{chapter_title}"
                Chapter description: {chapter_description}

                This should be a cohesive section focusing specifically on this area of the user's life.
                """
            elif chapter:
                # Handle case when LifeChapter doesn't exist but chapter is specified
                chapter_title = chapter
                chapter_content = f"""
                Focus on generating content for the chapter: "{chapter_title}"
                This should be a cohesive section focusing specifically on this area of the user's life.
                """

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROK_API_KEY}',
                'X-Request-ID': str(request_id)
            }

            prompt = f"""
            Generate a thoughtful, biographical narrative based on the user's journal entries.

            USER'S JOURNAL ENTRIES (sample):
            {entries_text}

            USER'S INSIGHTS:
            {insights_text}

            {chapter_content}

            Guidelines:
            1. Write in third person, as if this is a biography about the person's life
            2. Maintain a respectful, reflective tone
            3. Extract themes, patterns, and significant events from their entries
            4. Create a coherent narrative that captures their personality and experiences
            5. Avoid inventing major life events not supported by the entries
            6. Use elegant, thoughtful language appropriate for a biographical work
            7. Organize content into meaningful paragraphs with good flow
            8. Length should be approximately 800-1200 words
            """

            payload = {
                'model': 'llama3-70b-8192',
                'messages': [
                    {'role': 'system', 'content': 'You are a skilled biographer who creates compelling life narratives based on journal entries.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.7,
                'max_tokens': 1500
            }

            start_time = time.time()
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30  # Biography generation needs more time
            )
            api_time = time.time() - start_time

            logger.info(f"Biography generation {request_id} completed in {api_time:.2f}s with status {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Biography generation {request_id} failed: {response.status_code} - {response.text}")
                raise RequestException(f"API returned status code {response.status_code}")

            response_data = response.json()

            # Validate response structure
            if 'choices' not in response_data or not response_data['choices']:
                error_msg = f"Invalid API response structure: {response_data}"
                logger.error(f"Biography generation {request_id}: {error_msg}")
                raise ValueError(error_msg)

            biography_content = response_data['choices'][0]['message']['content']

            # Store the generated biography or chapter
            if chapter:
                # Get most recent biography or create a new one
                biography = Biography.objects.filter(user=user).order_by('-updated_at').first()
                if not biography:
                    biography = Biography(
                        user=user,
                        title="My Life Story",
                        content="",
                        time_period_start=timezone.now().date() - timezone.timedelta(days=365*5),  # Last 5 years
                        time_period_end=timezone.now().date()
                    )
                    biography.save()

                # Update the specific chapter content in the biography object
                chapter_key = chapter.lower().replace(' ', '_')
                chapters_data = biography.chapters_data or {}
                chapters_data[chapter_key] = {
                    'title': chapter,
                    'content': biography_content,
                    'last_updated': timezone.now().isoformat()
                }
                biography.chapters_data = chapters_data
                biography.save()

                return biography_content
            else:
                # Get most recent biography or create a new one
                biography = Biography.objects.filter(user=user).order_by('-updated_at').first()
                if not biography:
                    biography = Biography(
                        user=user,
                        title="My Life Story",
                        time_period_start=timezone.now().date() - timezone.timedelta(days=365*5),  # Last 5 years
                        time_period_end=timezone.now().date()
                    )

                biography.content = biography_content
                biography.save()

                # Auto-classify biography into chapters
                auto_chapters = AIService._auto_classify_biography_into_chapters(biography_content, user)

                # If we already have chapters_data, merge with new data
                if biography.chapters_data:
                    chapters_data = biography.chapters_data
                    for key, value in auto_chapters.items():
                        chapters_data[key] = value
                else:
                    chapters_data = auto_chapters

                biography.chapters_data = chapters_data
                biography.save()

                # If we have LifeChapter model and no chapters exist, create default ones based on the auto-classification
                if has_life_chapters and not LifeChapter.objects.filter(user=user).exists():
                    standard_chapters = {
                        "childhood": "Childhood",
                        "education": "Education",
                        "career": "Career",
                        "relationships": "Relationships",
                        "personal_growth": "Personal Growth",
                        "recent_years": "Recent Years"
                    }

                    for key, title in standard_chapters.items():
                        if key in chapters_data and chapters_data[key].get('content'):
                            # Create the chapter if it has content
                            LifeChapter.objects.create(
                                user=user,
                                title=title,
                                time_period=f"Your {title.lower()} period",
                                description=f"This chapter covers your {title.lower()} experiences."
                            )

                return biography_content

        except Exception as e:
            logger.error(f"Biography generation {request_id} error: {str(e)}", exc_info=True)
            if chapter:
                return f"Unable to generate the '{chapter}' chapter at this time. Please try again later."
            else:
                return "Unable to generate your biography at this time. Please try again later."

    @staticmethod
    def _auto_classify_biography_into_chapters(biography_content, user):
        """
        Automatically classify a biography into standard chapters.
        This uses AI to identify and separate content into appropriate life chapters.
        """
        # Import models here to avoid circular imports
        from django.apps import apps
        from django.utils import timezone
        import json
        import re
        import time
        import requests
        from django.conf import settings

        request_id = int(time.time() * 1000)
        logger.info(f"Auto-classification {request_id} started for user {user.username}")

        try:
            # Standard chapter categories
            standard_chapters = [
                "Childhood",
                "Education",
                "Career",
                "Relationships",
                "Personal Growth",
                "Recent Years"
            ]

            # Create prompt for classification
            classification_prompt = f"""
            I have a biography text that needs to be separated into the following chapters:

            {', '.join(standard_chapters)}

            Please read the biography and extract content relevant to each chapter.
            For each chapter, return only the content that belongs to that specific chapter.

            Format the response as JSON with the following structure:
            {{
                "childhood": {{ "content": "extracted content for childhood chapter here" }},
                "education": {{ "content": "extracted content for education chapter here" }},
                "career": {{ "content": "extracted content for career chapter here" }},
                "relationships": {{ "content": "extracted content for relationships chapter here" }},
                "personal_growth": {{ "content": "extracted content for personal growth chapter here" }},
                "recent_years": {{ "content": "extracted content for recent years chapter here" }}
            }}

            Here is the biography to classify:

            {biography_content}
            """

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROK_API_KEY}',
                'X-Request-ID': str(request_id)
            }

            payload = {
                'model': 'llama3-70b-8192',
                'messages': [
                    {'role': 'system', 'content': 'You are an expert at analyzing and organizing biographies into thematic chapters.'},
                    {'role': 'user', 'content': classification_prompt}
                ],
                'temperature': 0.3,  # Lower temperature for more deterministic output
                'max_tokens': 1500
            }

            start_time = time.time()
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            api_time = time.time() - start_time

            logger.info(f"Auto-classification {request_id} completed in {api_time:.2f}s with status {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Auto-classification {request_id} failed: {response.status_code} - {response.text}")
                return {}

            response_data = response.json()

            # Extract the JSON content from the response
            content = response_data['choices'][0]['message']['content']

            # Try to extract JSON from the response

            # First try to extract JSON from code blocks
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # If no code block, look for opening and closing braces
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                else:
                    # No JSON found
                    logger.error(f"Auto-classification {request_id}: No JSON found in response")
                    return {}

            try:
                chapters_data = json.loads(json_str)

                # Ensure all keys are properly formatted
                formatted_data = {}
                for chapter in standard_chapters:
                    key = chapter.lower().replace(' ', '_')
                    normalized_key = key.replace('-', '_')

                    # Check for various possible keys
                    if key in chapters_data:
                        formatted_data[key] = chapters_data[key]
                    elif normalized_key in chapters_data:
                        formatted_data[key] = chapters_data[normalized_key]
                    elif chapter.lower() in chapters_data:
                        formatted_data[key] = chapters_data[chapter.lower()]
                    elif chapter in chapters_data:
                        formatted_data[key] = chapters_data[chapter]

                # Add timestamps to each chapter
                current_time = timezone.now().isoformat()
                for key in formatted_data:
                    if isinstance(formatted_data[key], dict) and 'content' in formatted_data[key]:
                        formatted_data[key]['last_updated'] = current_time
                    else:
                        # If it's not a dict with content (just text or wrong format), convert to proper format
                        if isinstance(formatted_data[key], dict):
                            content_value = formatted_data[key].get('content', str(formatted_data[key]))
                        else:
                            content_value = str(formatted_data[key])

                        formatted_data[key] = {
                            'content': content_value,
                            'last_updated': current_time
                        }

                return formatted_data

            except json.JSONDecodeError:
                logger.error(f"Auto-classification {request_id}: JSON parsing error: {json_str}")
                return {}

        except Exception as e:
            logger.error(f"Auto-classification {request_id} error: {str(e)}", exc_info=True)
            return {}

    # ========================================================================
    # NEW METHODS FOR SMART JOURNAL COMPILER
    # ========================================================================

    @staticmethod
    def generate_journal_analysis(user: User, entries) -> str:
        """Generate AI-powered analysis of journal entries for compilation"""

        try:
            # Prepare entry data for analysis
            entry_data = []
            for entry in entries[:50]:  # Limit to recent 50 entries
                entry_data.append({
                    'title': entry.title,
                    'content': entry.content[:500],  # First 500 chars
                    'mood': entry.mood,
                    'date': entry.created_at.strftime('%Y-%m-%d'),
                    'tags': [tag.name for tag in entry.tags.all()]
                })

            analysis_prompt = f"""
Analyze this collection of journal entries and provide insights about:

1. Dominant themes and patterns
2. Emotional journey and growth
3. Writing style and voice
4. Key life events or transformations
5. Potential story arcs or narratives
6. Publication potential and market appeal

Journal Entries Data:
{json.dumps(entry_data[:10], indent=2)}

Provide a comprehensive but concise analysis (300-400 words) that would help the author understand their journaling patterns and identify potential publication opportunities.

Focus on:
- What makes these entries unique and compelling
- Natural story progressions or themes
- Emotional depth and authenticity
- Potential reader appeal
"""

            if user.is_authenticated:
                response = generate_ai_content_personalized(analysis_prompt, user)
            else:
                response = generate_ai_content(analysis_prompt)

            return response.get('entry', 'Analysis completed successfully')

        except Exception as e:
            logger.error(f"Error generating journal analysis: {e}")
            return "Unable to generate detailed analysis at this time. Basic analysis completed successfully."

    @staticmethod
    def generate_journal_structure(user: User, entries, analysis: Dict, journal_type: str, compilation_method: str) -> Dict:
        """Generate AI-powered journal structure"""

        try:
            # Prepare context for AI
            context = {
                'journal_type': journal_type,
                'compilation_method': compilation_method,
                'entry_count': len(entries),
                'dominant_themes': [theme['name'] for theme in analysis.get('themes', [])[:5]],
                'quality_score': analysis.get('quality_score', {}).get('score', 0),
                'date_range': analysis.get('date_range', {}),
                'story_arcs': len(analysis.get('story_arcs', []))
            }

            structure_prompt = f"""
Create a compelling journal structure for publication based on this analysis:

Context: {json.dumps(context, indent=2)}

Generate a journal structure with:
1. Compelling title (based on journal type: {journal_type})
2. Engaging description for potential readers
3. 3-6 well-organized chapters with:
   - Meaningful chapter titles
   - Brief chapter descriptions
   - Logical flow and progression
4. Consider the compilation method: {compilation_method}

Format your response as JSON:
{{
    "title": "Suggested Journal Title",
    "description": "Marketing description for readers",
    "chapters": [
        {{
            "title": "Chapter Title",
            "description": "What this chapter covers",
            "theme": "primary theme",
            "estimated_entries": 5
        }}
    ],
    "target_audience": "Who would enjoy this journal",
    "unique_selling_points": ["USP 1", "USP 2", "USP 3"]
}}

Make it compelling and marketable while staying authentic to the author's voice.
The structure should feel natural and engaging for readers.
"""

            response = AIService._get_groq_response(structure_prompt)

            # Parse AI response
            try:
                json_text = AIService.extract_json_from_text(response)
                structure = json.loads(json_text)
            except json.JSONDecodeError:
                # Fallback structure if JSON parsing fails
                structure = AIService._create_fallback_structure(journal_type, analysis)

            # Validate and enhance structure
            structure = AIService._validate_and_enhance_structure(structure, entries, analysis)

            return structure

        except Exception as e:
            logger.error(f"Error generating journal structure: {e}")
            return AIService._create_fallback_structure(journal_type, analysis)

    @staticmethod
    def _create_fallback_structure(journal_type: str, analysis: Dict) -> Dict:
        """Create fallback structure when AI generation fails"""

        # Template structures based on journal type
        templates = {
            'growth': {
                'title': 'My Personal Growth Journey',
                'description': 'A candid exploration of personal development, challenges overcome, and lessons learned along the way.',
                'chapters': [
                    {'title': 'Where I Started', 'description': 'Setting the foundation for change'},
                    {'title': 'Facing Challenges', 'description': 'Obstacles and how I navigated them'},
                    {'title': 'Breakthrough Moments', 'description': 'Key realizations and turning points'},
                    {'title': 'Growth and Reflection', 'description': 'Lessons learned and future aspirations'}
                ]
            },
            'travel': {
                'title': 'Adventures and Discoveries',
                'description': 'A journey through new places, cultures, and experiences that shaped my perspective.',
                'chapters': [
                    {'title': 'Departure', 'description': 'Leaving familiar territory behind'},
                    {'title': 'New Horizons', 'description': 'First encounters with the unknown'},
                    {'title': 'Deep Immersion', 'description': 'Living like a local and unexpected discoveries'},
                    {'title': 'Coming Home', 'description': 'Reflections on how travel changed me'}
                ]
            },
            'career': {
                'title': 'Professional Evolution',
                'description': 'Navigating career transitions, professional growth, and finding purpose in work.',
                'chapters': [
                    {'title': 'Career Crossroads', 'description': 'Recognizing the need for change'},
                    {'title': 'Taking the Leap', 'description': 'Bold moves and calculated risks'},
                    {'title': 'Learning and Adapting', 'description': 'Developing new skills and perspectives'},
                    {'title': 'New Professional Identity', 'description': 'Embracing change and future goals'}
                ]
            }
        }

        template = templates.get(journal_type, templates['growth'])

        # Customize based on analysis
        themes = analysis.get('themes', [])
        if themes:
            dominant_theme = themes[0]['name']
            template['title'] = f"My {dominant_theme.title()} Journey"

        template['target_audience'] = f"Readers interested in {journal_type} and personal development"
        template['unique_selling_points'] = [
            "Authentic personal narrative",
            "Real experiences and honest reflections",
            "Practical insights and lessons learned"
        ]

        return template

    @staticmethod
    def _validate_and_enhance_structure(structure: Dict, entries, analysis: Dict) -> Dict:
        """Validate and enhance the AI-generated structure"""

        # Ensure required fields exist
        if 'title' not in structure:
            structure['title'] = 'My Personal Journal'

        if 'description' not in structure:
            structure['description'] = 'A collection of personal reflections and experiences.'

        if 'chapters' not in structure or not structure['chapters']:
            structure['chapters'] = [
                {
                    'title': 'My Journey',
                    'description': 'Personal reflections and experiences',
                    'theme': 'general',
                    'estimated_entries': len(entries)
                }
            ]

        # Assign entries to chapters
        entries_list = list(entries.order_by('created_at'))
        entries_per_chapter = len(entries_list) // len(structure['chapters'])

        for i, chapter in enumerate(structure['chapters']):
            start_idx = i * entries_per_chapter
            if i == len(structure['chapters']) - 1:  # Last chapter gets remaining entries
                chapter_entries = entries_list[start_idx:]
            else:
                end_idx = start_idx + entries_per_chapter
                chapter_entries = entries_list[start_idx:end_idx]

            chapter['entry_ids'] = [entry.id for entry in chapter_entries]
            chapter['entry_count'] = len(chapter_entries)

        # Add metadata
        structure['compilation_method'] = 'ai'
        structure['generated_at'] = timezone.now().isoformat()
        structure['total_entries'] = len(entries)

        return structure

    @staticmethod
    def generate_chapter_introduction(chapter_title: str, chapter_description: str, user: User) -> str:
        """Generate AI introduction for a chapter"""

        try:
            intro_prompt = f"""
Write a compelling introduction for a journal chapter titled "{chapter_title}".

Chapter Description: {chapter_description}

Create a warm, engaging introduction (150-200 words) that:
1. Sets the context for this chapter
2. Prepares readers for what they'll discover
3. Creates emotional connection
4. Maintains an authentic, personal tone

The introduction should feel like the author is personally speaking to the reader,
drawing them into this part of their journey.
"""

            response = AIService._get_groq_response(intro_prompt)
            return response

        except Exception as e:
            logger.error(f"Error generating chapter introduction: {e}")
            return f"Welcome to {chapter_title}. In this chapter, we explore {chapter_description.lower()}."

    @staticmethod
    def generate_reflection_questions(journal_type: str, user: User) -> str:
        """Generate reflection questions for readers"""

        try:
            questions_prompt = f"""
Create 8-10 thoughtful reflection questions for readers of a {journal_type} journal.

These questions should:
1. Help readers connect with the content personally
2. Encourage deep self-reflection
3. Be open-ended and thought-provoking
4. Relate specifically to {journal_type} themes
5. Be suitable for personal journaling or group discussion

Format as a numbered list with brief explanations for each question.
Make them meaningful and actionable.
"""

            response = AIService._get_groq_response(questions_prompt)
            return response

        except Exception as e:
            logger.error(f"Error generating reflection questions: {e}")
            return AIService._get_default_reflection_questions(journal_type)

    @staticmethod
    def _get_default_reflection_questions(journal_type: str) -> str:
        """Get default reflection questions by type"""

        questions_by_type = {
            'growth': """
1. What patterns do you notice in your own growth journey?
2. Which challenges mentioned resonate most with your experience?
3. How do you typically handle difficult transitions?
4. What would you tell your past self about facing fears?
5. Which insights could you apply to your current situation?
6. How has your definition of success evolved over time?
7. What role does self-reflection play in your personal growth?
8. How do you maintain motivation during challenging periods?
""",
            'travel': """
1. How do new experiences change your perspective on home?
2. What travel experiences have shaped your worldview most?
3. How do you handle uncertainty when exploring new places?
4. What connections have you made with people from different cultures?
5. How has travel influenced your personal growth?
6. What fears have you overcome through your adventures?
7. How do you balance planning with spontaneity when traveling?
8. What travel memories do you find yourself returning to often?
""",
            'career': """
1. How do you define professional fulfillment?
2. What role does passion play in your career decisions?
3. How do you handle professional setbacks and failures?
4. What skills have been most valuable in your career journey?
5. How do you balance personal values with professional demands?
6. What career advice would you give to someone starting out?
7. How has your relationship with work evolved over time?
8. What legacy do you want to leave through your professional work?
"""
        }

        return questions_by_type.get(journal_type, questions_by_type['growth'])

    @staticmethod
    def generate_thematic_connections(structure: Dict, user: User) -> str:
        """Generate thematic connections between chapters"""

        try:
            chapters = structure.get('chapters', [])
            chapter_themes = [chapter.get('theme', chapter.get('title', '')) for chapter in chapters]

            connections_prompt = f"""
Identify and explain the thematic connections between these journal chapters:

Chapters: {', '.join(chapter_themes)}

Write a brief guide (200-250 words) that:
1. Shows how the chapters connect thematically
2. Highlights the overall narrative arc
3. Helps readers understand the progression
4. Points out recurring themes and motifs

Keep it insightful but accessible, helping readers see the deeper patterns
in the author's journey.
"""

            response = AIService._get_groq_response(connections_prompt)
            return response

        except Exception as e:
            logger.error(f"Error generating thematic connections: {e}")
            return 'The chapters in this journal are connected by themes of growth, discovery, and personal transformation.'

    @staticmethod
    def generate_readers_guide(structure: Dict, user: User) -> str:
        """Generate a reader's guide for the journal"""

        try:
            journal_title = structure.get('title', 'Journal')
            journal_type = structure.get('journal_type', 'personal')
            chapter_count = len(structure.get('chapters', []))

            guide_prompt = f"""
Create a reader's guide for "{journal_title}" - a {journal_type} journal with {chapter_count} chapters.

The guide should include:
1. How to get the most out of reading this journal
2. Suggested reading approach (linear vs. selective)
3. How to use this journal for personal reflection
4. Discussion questions for book clubs or personal use
5. Related topics for further exploration

Keep it practical and encouraging (300-400 words).
Make it feel like helpful advice from a friend.
"""

            response = AIService._get_groq_response(guide_prompt)
            return response

        except Exception as e:
            logger.error(f"Error generating readers guide: {e}")
            return AIService._get_default_readers_guide(journal_title)

    @staticmethod
    def _get_default_readers_guide(journal_title: str) -> str:
        """Get default reader's guide"""

        return f"""
# Reader's Guide to "{journal_title}"

## How to Read This Journal

This journal is designed to be both a personal narrative and a source of inspiration for your own journey. You can read it from beginning to end to follow the complete story arc, or focus on specific chapters that resonate with your current situation.

## Getting the Most from Your Reading

- Take your time with each entry
- Keep a notebook handy for your own reflections
- Consider how the experiences relate to your own life
- Don't hesitate to re-read sections that particularly speak to you

## For Personal Reflection

Use this journal as a mirror for your own experiences. After reading each chapter, spend a few minutes reflecting on how the themes and experiences connect to your own life journey.

## For Discussion Groups

This journal works well for book clubs and discussion groups. Each chapter can spark meaningful conversations about personal growth, life transitions, and shared human experiences.

## Further Exploration

Consider starting your own journaling practice inspired by what you've read. The act of writing about your experiences can be just as transformative as reading about others'.
"""

    @staticmethod
    def analyze_marketability(entries, analysis: Dict) -> Dict:
        """Analyze the marketability potential of entries"""

        try:
            marketability_prompt = f"""
Analyze the marketability potential of a journal collection with these characteristics:

- Total entries: {len(entries)}
- Quality score: {analysis.get('quality_score', {}).get('score', 'N/A')}
- Main themes: {[theme['name'] for theme in analysis.get('themes', [])[:5]]}
- Writing consistency: {analysis.get('writing_patterns', {}).get('writing_frequency', 'unknown')}

Provide analysis on:
1. Market appeal (1-10 scale with explanation)
2. Target audience description
3. Competitive positioning
4. Pricing recommendations
5. Marketing angles

Be realistic but encouraging. Focus on what makes this collection unique.
"""

            response = AIService._get_groq_response(marketability_prompt)

            # Extract insights (simplified - you could use more sophisticated parsing)
            return {
                'analysis': response,
                'market_appeal': 7,  # Default
                'target_audience': 'Personal development readers',
                'suggested_price_range': (4.99, 14.99)
            }

        except Exception as e:
            logger.error(f"Error analyzing marketability: {e}")
            return {
                'analysis': 'Marketability analysis temporarily unavailable',
                'market_appeal': 7,
                'target_audience': 'General audience interested in personal stories',
                'suggested_price_range': (4.99, 12.99)
            }

    @staticmethod
    def generate_marketing_copy(journal) -> Dict:
        """Generate marketing copy for a published journal"""

        try:
            marketing_prompt = f"""
Create compelling marketing copy for this journal:

Title: {journal.title}
Description: {journal.description}
Author: {journal.author.username}
Entry Count: {getattr(journal, 'entries', {}).count() if hasattr(journal, 'entries') else 'Multiple'} entries

Generate:
1. Catchy tagline (10-15 words)
2. Short description for listings (50-80 words)
3. Social media post (Twitter-length)
4. Email subject line for newsletters

Make it engaging and authentic while highlighting the unique value.
Focus on emotional connection and reader benefits.
"""

            response = AIService._get_groq_response(marketing_prompt)

            return {
                'marketing_copy': response,
                'generated': True
            }

        except Exception as e:
            logger.error(f"Error generating marketing copy: {e}")
            return {
                'marketing_copy': 'Discover authentic stories and personal insights in this compelling journal.',
                'generated': False
            }

    # ========================================================================
    # EXISTING METHODS FOR BACKWARDS COMPATIBILITY
    # ========================================================================

    @staticmethod
    def generate_conversational_response(prompt):
        """
        Generate a conversational response using your existing AI helpers
        """
        try:
            # Use your existing generate_ai_content function
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
    def _get_groq_response(prompt, model="llama3-70b-8192", temperature=0.7, max_tokens=1000):
        """
        Get a response from the Groq API

        Args:
            prompt (str): The prompt to send to the API
            model (str): The model to use (default: llama3-70b-8192)
            temperature (float): Randomness parameter (default: 0.7)
            max_tokens (int): Maximum number of tokens to generate (default: 1000)

        Returns:
            str: The generated text response
        """
        try:
            import requests
            import time
            from django.conf import settings

            request_id = int(time.time() * 1000)

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROK_API_KEY}',  # Using GROK_API_KEY from settings
                'X-Request-ID': str(request_id)
            }

            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'You are a helpful assistant.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': temperature,
                'max_tokens': max_tokens
            }

            start_time = time.time()
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            api_time = time.time() - start_time

            logger.info(f"Groq API request {request_id} completed in {api_time:.2f}s with status {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Groq API request {request_id} failed: {response.status_code} - {response.text}")
                raise RequestException(f"API returned status code {response.status_code}")

            response_data = response.json()

            # Validate response structure
            if 'choices' not in response_data or not response_data['choices']:
                error_msg = f"Invalid API response structure: {response_data}"
                logger.error(f"Groq API request {request_id}: {error_msg}")
                raise ValueError(error_msg)

            return response_data['choices'][0]['message']['content']

        except Exception as e:
            logger.error(f"Error in _get_groq_response: {str(e)}", exc_info=True)
            raise
