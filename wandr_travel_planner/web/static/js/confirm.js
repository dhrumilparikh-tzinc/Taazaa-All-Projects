// confirm.js — Pre-fill form from URL params, POST /api/plan, navigate to /planning

const params = new URLSearchParams(window.location.search);

document.getElementById('city').value     = params.get('city') || '';
document.getElementById('country').value  = params.get('country') || '';
document.getElementById('days').value     = params.get('days') || '';
document.getElementById('budget').value   = params.get('budget') || '';
document.getElementById('currency').value = params.get('currency') || 'USD';
document.getElementById('month').value    = params.get('month') || '';
document.getElementById('interests').value= params.get('interests') || '';

const startBtn  = document.getElementById('start-btn');
const errorMsg  = document.getElementById('error-msg');

startBtn.addEventListener('click', async () => {
  const city     = document.getElementById('city').value.trim();
  const country  = document.getElementById('country').value.trim() || null;
  const days     = parseInt(document.getElementById('days').value, 10);
  const budget   = parseFloat(document.getElementById('budget').value) || null;
  const currency = document.getElementById('currency').value.trim().toUpperCase() || null;
  const month    = document.getElementById('month').value.trim() || null;
  const interests= document.getElementById('interests').value
                     .split(',').map(s => s.trim()).filter(Boolean);
  const query    = params.get('query') || '';

  if (!city || !days || days < 1) {
    showError('Please fill in city and duration.');
    return;
  }

  startBtn.disabled = true;
  startBtn.textContent = 'Starting…';
  hideError();

  try {
    const res = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        destination_city: city,
        destination_country: country,
        trip_duration_days: days,
        budget_amount: budget,
        budget_currency: currency,
        interests,
        travel_month: month,
        original_query: query,
      }),
    });

    if (!res.ok) {
      showError('Failed to start planning. Please try again.');
      startBtn.disabled = false;
      startBtn.textContent = 'Start planning';
      return;
    }

    const { trip_id } = await res.json();
    window.location.href = `/planning?id=${trip_id}`;
  } catch (err) {
    showError('Network error — please check your connection.');
    startBtn.disabled = false;
    startBtn.textContent = 'Start planning';
  }
});

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.classList.remove('hidden');
}
function hideError() {
  errorMsg.classList.add('hidden');
}
