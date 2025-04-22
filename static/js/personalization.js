// Add this to a new file: static/js/personalization.js

// Function to toggle personalization options in the journal form
function togglePersonalization() {
    const personalizationToggle = document.getElementById('personalizationToggle');
    const personalizationOptions = document.getElementById('personalizationOptions');

    if (personalizationToggle && personalizationOptions) {
      if (personalizationToggle.checked) {
        personalizationOptions.classList.remove('hidden');
      } else {
        personalizationOptions.classList.add('hidden');
      }
    }
  }

  // Update the generateDemo function to include personalization
  function generateDemo() {
    // Reset form state
    resetFormState();

    const journalContent = document.getElementById('journalInput').value.trim();

    // Validate input
    if (journalContent.length < 10) {
      alert('Please share a bit more about your day (at least 10 characters)');
      return;
    }

    // Check if personalization is enabled
    const usePersonalization = document.getElementById('personalizationToggle') &&
                               document.getElementById('personalizationToggle').checked;

    // Show loading indicator
    document.getElementById('loadingIndicator').classList.remove('hidden');
    document.getElementById('demoButton').disabled = true;
    document.getElementById('signupPrompt').classList.add('hidden');

    // Get CSRF token for Django
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    // Prepare request payload
    const payload = {
      journal_content: journalContent,
      personalize: usePersonalization
    };

    // Call your backend API
    fetch('/api/demo-journal/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify(payload)
    })
    .then(response => {
      if (!response.ok) {
        if (response.status === 429) {
          throw new Error('Rate limit exceeded. Please wait a moment before trying again.');
        }
        throw new Error('Server error: ' + response.status);
      }
      return response.json();
    })
    .then(data => {
      // Hide loading indicator
      document.getElementById('loadingIndicator').classList.add('hidden');

      if (data.error) {
        alert('Error: ' + data.error);
        restartDemo();
        return;
      }

      // Display the AI-generated result
      document.getElementById('journalEntry').innerHTML = data.entry.replace(/\n/g, '<br>');
      document.getElementById('entryTitle').textContent = data.title || "My Journal Entry";

      // Add personalization badge if it was personalized
      const resultHeader = document.querySelector('#resultPreview .p-6');
      if (data.personalized && resultHeader) {
        // Remove existing badge if any
        const existingBadge = resultHeader.querySelector('.personalization-badge');
        if (existingBadge) {
          existingBadge.remove();
        }

        // Add new badge
        const badge = document.createElement('span');
        badge.className = 'personalization-badge ml-2 bg-secondary-100 text-secondary-800 text-xs px-2 py-1 rounded-full';
        badge.innerHTML = '<svg class="inline-block h-3 w-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>Personalized';

        const titleElement = resultHeader.querySelector('h3');
        if (titleElement) {
          titleElement.appendChild(badge);
        }
      }

      // Show the result preview
      document.getElementById('resultPreview').classList.remove('hidden');

      // Scroll to the result
      setTimeout(() => {
        document.getElementById('resultPreview').scrollIntoView({ behavior: 'smooth' });
      }, 100);

      // Enable the button
      document.getElementById('demoButton').disabled = false;
    })
    .catch(error => {
      console.error('Error:', error);
      alert(error.message || 'Sorry, we encountered an error. Please try again later.');
      document.getElementById('loadingIndicator').classList.add('hidden');
      document.getElementById('demoButton').disabled = false;
    });
  }

  // Initialize personalization controls
  document.addEventListener('DOMContentLoaded', function() {
    const personalizationToggle = document.getElementById('personalizationToggle');

    if (personalizationToggle) {
      personalizationToggle.addEventListener('change', togglePersonalization);
      // Initialize state
      togglePersonalization();
    }
  });
