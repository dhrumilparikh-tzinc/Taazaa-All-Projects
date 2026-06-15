// landing.js — Submit query, handle guardrail rejection, navigate to /confirm

const queryInput = document.getElementById('query-input');
const planBtn    = document.getElementById('plan-btn');
const errorMsg   = document.getElementById('error-msg');
const loading    = document.getElementById('loading');

function fillExample(btn) {
  queryInput.value = btn.textContent.trim();
  queryInput.focus();
}

// Submit on Ctrl+Enter / Cmd+Enter inside textarea
queryInput.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submitQuery();
});

planBtn.addEventListener('click', submitQuery);

async function submitQuery() {
  const query = queryInput.value.trim();
  if (!query) {
    showError('Please describe your trip first.');
    return;
  }

  setLoading(true);
  hideError();

  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });

    if (res.status === 403) {
      const data = await res.json();
      showError(data.detail?.message || "I can only help plan trips. Please describe a travel request.");
      setLoading(false);
      return;
    }

    if (!res.ok) {
      showError('Something went wrong. Please try again.');
      setLoading(false);
      return;
    }

    const parsed = await res.json();

    // Encode parsed values + original query as URL params for the confirm screen
    const params = new URLSearchParams({
      city:     parsed.destination_city || '',
      country:  parsed.destination_country || '',
      days:     parsed.trip_duration_days || '',
      budget:   parsed.budget_amount || '',
      currency: parsed.budget_currency || '',
      month:    parsed.travel_month || '',
      interests:parsed.interests.join(','),
      query:    query,
    });

    window.location.href = `/confirm?${params.toString()}`;
  } catch (err) {
    showError('Network error — please check your connection.');
    setLoading(false);
  }
}

function setLoading(on) {
  loading.classList.toggle('hidden', !on);
  planBtn.disabled = on;
  planBtn.classList.toggle('opacity-50', on);
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.classList.remove('hidden');
}

function hideError() {
  errorMsg.classList.add('hidden');
}
