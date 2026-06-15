// brief.js — Fetch /api/plan/{id}/result and render all five sections

async function loadBrief() {
  const res = await fetch(`/api/plan/${TRIP_ID}/result`);
  if (!res.ok) {
    document.getElementById('loading').innerHTML =
      '<p class="text-error">Could not load your trip brief. Please try again.</p>';
    return;
  }
  const state = await res.json();
  document.getElementById('loading').classList.add('hidden');
  renderOverview(state.destination_info);
  renderWeather(state.weather_data);
  renderBudget(state.budget_breakdown);
  renderItinerary(state.itinerary);
  renderPacking(state.packing_list);
}

function sectionHead(icon, title) {
  return `<div class="flex items-center gap-3 mb-6">
    <span class="material-symbols-outlined text-primary text-2xl">${icon}</span>
    <h2 class="font-serif text-3xl font-bold text-primary">${title}</h2>
  </div>`;
}

function renderOverview(info) {
  if (!info || info.error) return;
  const sec = document.getElementById('overview');
  sec.innerHTML = `
    ${sectionHead('travel_explore', info.country_name + ' ' + (info.flag || ''))}
    <div class="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
      ${metaCard('Capital', info.capital)}
      ${metaCard('Currency', info.currency_code + ' — ' + info.currency_name)}
      ${metaCard('Languages', (info.languages || []).join(', '))}
      ${metaCard('Timezone', info.timezone)}
      ${metaCard('Region', info.region + ', ' + info.subregion)}
    </div>
    ${info.overview_paragraph_1 ? `<p class="text-on-surface leading-relaxed mb-3">${info.overview_paragraph_1}</p>` : ''}
    ${info.overview_paragraph_2 ? `<p class="text-on-surface leading-relaxed">${info.overview_paragraph_2}</p>` : ''}
  `;
  sec.classList.remove('hidden');
}

function metaCard(label, value) {
  return `<div class="bg-surface-dk rounded-xl px-4 py-3">
    <p class="text-xs text-on-variant mb-0.5">${label}</p>
    <p class="text-sm font-medium text-on-surface">${value || '—'}</p>
  </div>`;
}

function renderWeather(wd) {
  if (!wd || wd.error || !wd.daily_forecast) return;
  const days = wd.daily_forecast.map(d => `
    <div class="bg-surface-dk rounded-xl px-4 py-3 text-center">
      <p class="text-xs text-on-variant mb-1">${d.date.slice(5)}</p>
      <p class="text-lg font-semibold text-on-surface">${d.temp_max_c.toFixed(0)}&deg;</p>
      <p class="text-xs text-on-variant">${d.temp_min_c.toFixed(0)}&deg;</p>
      ${d.precipitation_mm > 0 ? `<p class="text-xs text-primary mt-1"><span class="material-symbols-outlined" style="font-size:12px">water_drop</span> ${d.precipitation_mm.toFixed(0)}mm</p>` : ''}
    </div>
  `).join('');
  const sec = document.getElementById('weather');
  sec.innerHTML = `
    ${sectionHead('partly_cloudy_day', '7-Day Forecast')}
    <p class="text-sm text-on-variant mb-4">${wd.city}, ${wd.country} &middot; ${wd.timezone}</p>
    <div class="grid grid-cols-7 gap-2">${days}</div>
  `;
  sec.classList.remove('hidden');
}

function renderBudget(bd) {
  if (!bd || bd.error) return;
  const cats = (bd.categories || []).map(c => `
    <tr class="border-b border-divider">
      <td class="py-3 text-sm capitalize">${c.name}</td>
      <td class="py-3 text-sm text-right font-medium">${c.daily_amount.toLocaleString()} ${bd.total_budget_local_currency}</td>
      <td class="py-3 text-sm text-on-variant pl-4">${c.description}</td>
    </tr>
  `).join('');
  const sec = document.getElementById('budget');
  sec.innerHTML = `
    ${sectionHead('payments', 'Budget Breakdown')}
    <div class="grid grid-cols-3 gap-3 mb-6">
      ${metaCard('Your budget', (bd.total_budget_native || 0).toLocaleString() + ' ' + bd.total_budget_native_currency)}
      ${metaCard('In local currency', (bd.total_budget_local || 0).toLocaleString() + ' ' + bd.total_budget_local_currency)}
      ${metaCard('Daily budget', (bd.daily_budget_local || 0).toLocaleString() + ' ' + bd.total_budget_local_currency)}
    </div>
    <table class="w-full">
      <thead>
        <tr class="border-b-2 border-divider">
          <th class="text-left text-xs text-on-variant font-medium pb-2">Category</th>
          <th class="text-right text-xs text-on-variant font-medium pb-2">Per day</th>
          <th class="text-left text-xs text-on-variant font-medium pb-2 pl-4">Notes</th>
        </tr>
      </thead>
      <tbody>${cats}</tbody>
    </table>
    ${bd.notes ? `<p class="mt-4 text-sm text-on-variant italic">${bd.notes}</p>` : ''}
  `;
  sec.classList.remove('hidden');
}

function periodIcon(period) {
  const icons = {
    'early morning': 'wb_twilight',
    'morning': 'wb_sunny',
    'late morning': 'light_mode',
    'lunch': 'restaurant',
    'afternoon': 'partly_cloudy_day',
    'late afternoon': 'wb_cloudy',
    'evening': 'nights_stay',
  };
  return icons[period] || 'schedule';
}

function renderItinerary(itin) {
  if (!itin || itin.error || !itin.days) return;

  const days = itin.days.map(d => {
    // Highlights strip
    const highlightsHtml = d.highlights && d.highlights.length
      ? `<div class="flex flex-wrap gap-2 mb-5">
          ${d.highlights.map(h => `
            <span class="inline-flex items-center gap-1 bg-primary/10 text-primary text-xs font-medium px-3 py-1 rounded-full">
              <span class="material-symbols-outlined" style="font-size:13px">star</span>
              ${h}
            </span>`).join('')}
         </div>`
      : '';

    // Segments
    const segsHtml = (d.segments || []).map(s => `
      <div class="flex gap-4 items-start py-4 border-b border-divider last:border-0">
        <!-- Time + icon column -->
        <div class="flex-shrink-0 w-28 text-right">
          <p class="text-xs text-on-variant font-medium leading-tight">${s.time || ''}</p>
          <div class="inline-flex items-center gap-1 mt-1 text-primary">
            <span class="material-symbols-outlined" style="font-size:15px">${periodIcon(s.period)}</span>
            <span class="text-xs uppercase tracking-wide font-medium">${s.period}</span>
          </div>
        </div>
        <!-- Content column -->
        <div class="flex-1 min-w-0">
          <div class="flex items-start justify-between gap-2 mb-1">
            <div>
              <p class="font-semibold text-on-surface text-sm">${s.activity}</p>
              <p class="text-xs text-primary font-medium flex items-center gap-1">
                <span class="material-symbols-outlined" style="font-size:13px">location_on</span>
                ${s.location}
              </p>
            </div>
            ${s.cost_note ? `<span class="flex-shrink-0 text-xs bg-surface-dk text-on-variant px-2 py-0.5 rounded-full whitespace-nowrap">${s.cost_note}</span>` : ''}
          </div>
          <p class="text-sm text-on-surface leading-relaxed mt-2">${s.description || ''}</p>
          ${s.tips ? `
            <div class="flex items-start gap-1.5 mt-2.5 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              <span class="material-symbols-outlined text-amber-500 flex-shrink-0" style="font-size:15px">lightbulb</span>
              <p class="text-xs text-amber-800 leading-relaxed">${s.tips}</p>
            </div>` : ''}
        </div>
      </div>
    `).join('');

    // Transport note
    const transportHtml = d.transport_note
      ? `<div class="flex items-center gap-2 mt-4 pt-4 border-t border-divider text-sm text-on-variant">
           <span class="material-symbols-outlined text-on-variant" style="font-size:16px">directions_transit</span>
           <span>${d.transport_note}</span>
         </div>`
      : '';

    return `
      <div class="bg-surface-dk rounded-2xl overflow-hidden">
        <!-- Day header -->
        <div class="bg-primary px-6 py-4 flex items-center justify-between">
          <div>
            <p class="text-white/70 text-xs uppercase tracking-widest font-medium">Day ${d.day}</p>
            <p class="font-serif text-xl font-bold text-white mt-0.5">${d.theme}</p>
          </div>
          <span class="text-white/30 font-serif text-4xl font-bold leading-none">${d.day}</span>
        </div>
        <!-- Highlights -->
        ${highlightsHtml ? `<div class="px-6 pt-4">${highlightsHtml}</div>` : ''}
        <!-- Segments -->
        <div class="px-6 pb-4">${segsHtml}${transportHtml}</div>
      </div>
    `;
  }).join('');

  const sec = document.getElementById('itinerary');
  sec.innerHTML = `
    ${sectionHead('map', 'Day-by-Day Itinerary')}
    ${itin.summary ? `<p class="text-on-variant mb-8 leading-relaxed">${itin.summary}</p>` : ''}
    <div class="space-y-6">${days}</div>
  `;
  sec.classList.remove('hidden');
}

function renderPacking(pl) {
  if (!pl || pl.error || !pl.categories) return;
  const cats = (pl.categories || []).map(c => {
    const items = (c.items || []).map(i => `<li class="text-sm text-on-surface">• ${i}</li>`).join('');
    return `<div>
      <p class="text-xs text-primary uppercase tracking-wider font-medium mb-2">${c.category}</p>
      <ul class="space-y-1">${items}</ul>
    </div>`;
  }).join('');
  const sec = document.getElementById('packing');
  sec.innerHTML = `
    ${sectionHead('luggage', 'Packing List')}
    <p class="text-sm text-on-variant mb-6">${pl.weather_summary || ''}</p>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-6">${cats}</div>
  `;
  sec.classList.remove('hidden');
}

loadBrief();
