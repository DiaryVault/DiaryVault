function generateAI() {
    fetch('/ai-entry/')
      .then(response => response.json())
      .then(data => {
        if (data.content) {
          document.getElementById("id_content").value = data.content;
        } else {
          alert("Error: " + data.error);
        }
      });
  }

  function regenerateSummary(entryId) {
    const spinner = document.getElementById(`spinner-${entryId}`);
    const summaryBox = document.getElementById(`summary-${entryId}`);
    spinner.classList.remove('hidden');
    summaryBox.textContent = "";

    animateDots(entryId);

    fetch(`/stream-summary/${entryId}/`)
      .then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");

        function read() {
          reader.read().then(({ done, value }) => {
            if (done) {
              spinner.classList.add('hidden');
              stopDots(entryId);
              return;
            }
            const chunk = decoder.decode(value, { stream: true });
            summaryBox.textContent += chunk;
            read();
          });
        }

        read();
      })
      .catch(err => {
        console.error("Streaming error:", err);
        summaryBox.textContent = "Something went wrong while generating the summary.";
        spinner.classList.add('hidden');
        stopDots(entryId);
      });
  }

  function restoreVersion(versionId, entryId) {
    const spinner = document.getElementById(`spinner-${entryId}`);
    const summaryBox = document.getElementById(`summary-${entryId}`);
    spinner.classList.remove('hidden');
    summaryBox.innerText = '';

    fetch(`/restore-summary/${versionId}/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    })
      .then(res => res.json())
      .then(data => {
        spinner.classList.add('hidden');
        if (data.summary) {
          summaryBox.innerHTML = `<span class="typewriter"><span>${data.summary}</span></span>`;
        } else {
          summaryBox.textContent = "Failed to restore summary.";
        }
      })
      .catch(() => {
        spinner.classList.add('hidden');
        summaryBox.textContent = "Something went wrong.";
      });
  }

  function scrollToEntry(entryId) {
    const el = document.getElementById(`entry-${entryId}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.classList.add('ring-2', 'ring-sky-400');
      setTimeout(() => el.classList.remove('ring-2', 'ring-sky-400'), 1000);
    }
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  let activeTag = null;

  function filterByTag(tag) {
    activeTag = tag;
    const entries = document.querySelectorAll('#chat-container > div');
    const buttons = document.querySelectorAll('.tag-filter');

    buttons.forEach(btn => {
      btn.classList.remove('bg-sky-200');
      if (btn.dataset.tag === tag) {
        btn.classList.add('bg-sky-200');
      }
    });

    entries.forEach(entry => {
      const tagMatch = entry.querySelector(`[data-tag="${tag}"]`);
      entry.style.display = tagMatch ? "block" : "none";
    });
  }

  function clearTagFilter() {
    activeTag = null;
    document.querySelectorAll('#chat-container > div').forEach(entry => {
      entry.style.display = "block";
    });
    document.querySelectorAll('.tag-filter').forEach(btn => btn.classList.remove('bg-sky-200'));
  }

  function filterEntries() {
    const input = document.getElementById("searchInput").value.toLowerCase();
    const items = document.querySelectorAll("#entryList li");

    items.forEach(item => {
      const text = item.textContent.toLowerCase();
      item.style.display = text.includes(input) ? "block" : "none";
    });

    if (activeTag) {
      filterByTag(activeTag);
    }
  }

  document.addEventListener("input", function (e) {
    if (e.target.tagName.toLowerCase() === "textarea") {
      e.target.style.height = "auto";
      e.target.style.height = e.target.scrollHeight + "px";
    }
  });

  const spinners = {};

  function animateDots(entryId) {
    const spinner = document.querySelector(`#spinner-${entryId} .dots`);
    if (!spinner) return;

    let count = 1;
    spinners[entryId] = setInterval(() => {
      spinner.textContent = '.'.repeat(count % 4);
      count++;
    }, 500);
  }

  function stopDots(entryId) {
    if (spinners[entryId]) {
      clearInterval(spinners[entryId]);
      delete spinners[entryId];
    }
  }
