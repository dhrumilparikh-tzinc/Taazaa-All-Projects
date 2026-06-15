// planning.js — Open SSE, update step indicators, redirect on completion

function getRow(agent) {
  return document.querySelector(`[data-agent="${agent}"]`);
}

function setState(agent, state, summary) {
  const row = getRow(agent);
  if (!row) return;
  const pending = row.querySelector('.pending-icon');
  const running = row.querySelector('.running-icon');
  const done    = row.querySelector('.done-icon');
  const error   = row.querySelector('.error-icon');
  const sumEl   = row.querySelector('.step-summary');

  pending.classList.add('hidden');
  running.classList.add('hidden');
  done.classList.add('hidden');
  error.classList.add('hidden');

  if (state === 'running')  running.classList.remove('hidden');
  if (state === 'done')     done.classList.remove('hidden');
  if (state === 'error')    error.classList.remove('hidden');
  if (state === 'pending')  pending.classList.remove('hidden');

  if (summary) sumEl.textContent = summary;
}

const statusLine = document.getElementById('status-line');

if (!TRIP_ID) {
  statusLine.textContent = 'No trip ID — please start from the beginning.';
} else {
  const es = new EventSource(`/api/plan/${TRIP_ID}/stream`);

  es.addEventListener('message', (e) => {
    const event = JSON.parse(e.data);
    const { type, agent, summary, status, feedback, attempt } = event;

    if (type === 'agent_started') {
      setState(agent, 'running', `Running… (attempt ${attempt})`);
      statusLine.textContent = `Working on ${agent}…`;
    }

    if (type === 'agent_retried') {
      setState(agent, 'running', `Retrying (attempt ${attempt})…`);
      statusLine.textContent = `Retrying ${agent}…`;
    }

    if (type === 'agent_completed') {
      const st = status === 'valid' ? 'done' : 'error';
      setState(agent, st, summary || (status === 'valid' ? 'Complete' : 'Accepted with warnings'));
    }

    if (type === 'agent_failed') {
      setState(agent, 'error', 'Failed after retries');
    }

    if (type === 'plan_complete') {
      statusLine.textContent = 'Your trip plan is ready!';
      es.close();
      setTimeout(() => {
        window.location.href = `/brief/${TRIP_ID}`;
      }, 800);
    }

    if (type === 'plan_error') {
      statusLine.textContent = `Planning failed: ${event.error}`;
      es.close();
    }
  });

  es.onerror = () => {
    statusLine.textContent = 'Connection lost. The plan may still complete — try refreshing.';
  };
}
