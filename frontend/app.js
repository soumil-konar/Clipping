let activeJobId = null;
let activeClip = null;
let systemProfiles = {};
let selectedGenre = 'sports';

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

async function initApp() {
  await fetchSystemStatus();
  fetchJobs();
  setupEventListeners();

  // Poll jobs list periodically
  setInterval(fetchJobs, 4000);
}

function setupEventListeners() {
  // Ingest form submission
  const form = document.getElementById('ingest-form');
  if (form) form.addEventListener('submit', handleIngestSubmit);

  // Content Genre AI Tuning Pills
  document.querySelectorAll('.genre-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      selectedGenre = pill.dataset.genre || 'sports';

      // Update genre hint text and flash animation
      const hintEl = document.getElementById('genre-hint-text');
      const hintBox = document.getElementById('genre-hint-box');
      if (hintEl && pill.dataset.hint) {
        hintEl.textContent = `Tuned for: ${pill.dataset.hint}`;
      }
      if (hintBox) {
        hintBox.classList.remove('hint-flash');
        void hintBox.offsetWidth; // trigger CSS reflow
        hintBox.classList.add('hint-flash');
      }

      // Update input bar badge & button label
      const firstSpan = pill.querySelector('span');
      const genreName = firstSpan ? firstSpan.textContent.trim() : pill.textContent.trim();
      const genreTag = document.getElementById('active-genre-tag');
      if (genreTag) {
        genreTag.textContent = genreName;
      }

      const btnText = document.getElementById('btn-submit-text');
      if (btnText) {
        btnText.textContent = `Generate ${genreName.split(' ')[1] || genreName} Clips`;
      }

      showToast(`AI tuned for ${genreName}`, '🎯');
    });
  });

  // Paste button
  const pasteBtn = document.getElementById('btn-paste');
  if (pasteBtn) {
    pasteBtn.addEventListener('click', async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          document.getElementById('stream-url').value = text.trim();
          showToast('Pasted URL from clipboard', '📋');
        }
      } catch (err) {
        console.warn('Clipboard read failed:', err);
      }
    });
  }

  // Inspector Tab Switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.dataset.tab;
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add('active');
    });
  });

  // Safe-Zone Grid Toggle
  const toggleOverlayBtn = document.getElementById('btn-toggle-overlay');
  if (toggleOverlayBtn) {
    toggleOverlayBtn.addEventListener('click', () => {
      const safeGrid = document.getElementById('safe-zone-grid');
      if (!safeGrid) return;
      const isHidden = safeGrid.classList.contains('hidden');
      if (isHidden) {
        safeGrid.classList.remove('hidden');
        toggleOverlayBtn.classList.add('active');
        document.getElementById('toggle-overlay-text').textContent = 'Hide Margins';
        showToast('Safe-zone margins displayed', '👁️');
      } else {
        safeGrid.classList.add('hidden');
        toggleOverlayBtn.classList.remove('active');
        document.getElementById('toggle-overlay-text').textContent = 'Safe Zones';
      }
    });
  }

  // Live Subtitle Color Picker
  const colorMap = {
    '&H00FFFF&': { hex: '#ffff00', name: 'Yellow' },
    '&H00FF00&': { hex: '#00ff88', name: 'Emerald' },
    '&HFFFF00&': { hex: '#00f0ff', name: 'Cyan' },
    '&H0000FF&': { hex: '#ff3344', name: 'Crimson' }
  };

  document.querySelectorAll('input[name="subtitle_color"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const info = colorMap[e.target.value] || { hex: '#ffff00', name: 'Yellow' };
      const highlightEl = document.getElementById('preview-highlight-word');
      if (highlightEl) {
        highlightEl.style.color = info.hex;
        highlightEl.style.textShadow = `0 0 10px ${info.hex}`;
        highlightEl.style.borderBottomColor = info.hex;
      }
      showToast(`Subtitle color: ${info.name}`, '🎨');
    });
  });

  // Settings Modal
  const settingsBtn = document.getElementById('btn-settings');
  const modal = document.getElementById('settings-modal');
  const closeBtn = document.getElementById('btn-close-modal');
  const saveSettingsBtn = document.getElementById('btn-save-settings');

  if (settingsBtn && modal) {
    settingsBtn.addEventListener('click', () => modal.classList.remove('hidden'));
    if (closeBtn) closeBtn.addEventListener('click', () => modal.classList.add('hidden'));
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  }

  if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', async () => {
      const key = document.getElementById('modal-gemini-key').value.trim();
      if (key) {
        await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gemini_api_key: key })
        });
        showToast('Gemini API key saved', '🔑');
      }
      if (modal) modal.classList.add('hidden');
      fetchSystemStatus();
    });
  }

  // Fine-tuning re-render
  const reRenderBtn = document.getElementById('btn-re-render');
  if (reRenderBtn) reRenderBtn.addEventListener('click', handleReRender);

  // Export / Download
  const downloadBtn = document.getElementById('btn-download-mp4');
  if (downloadBtn) downloadBtn.addEventListener('click', handleExport);

  // Trim inputs change listener
  ['trim-start', 'trim-end'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateDurationDisplay);
  });
}

async function fetchSystemStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const badge = document.getElementById('gpu-text');
    const encoderSpan = document.getElementById('settings-encoder');

    if (data.platform_profiles) {
      systemProfiles = data.platform_profiles;
    }

    if (data.cuda_available) {
      if (badge) badge.textContent = `RTX 3080 (${data.encoder})`;
      if (encoderSpan) encoderSpan.textContent = `NVIDIA NVENC (${data.encoder})`;
    } else {
      if (badge) badge.textContent = 'CPU Mode';
      if (encoderSpan) encoderSpan.textContent = 'CPU (libx264)';
    }
  } catch (err) {
    console.error('Status fetch error:', err);
  }
}

async function handleIngestSubmit(e) {
  e.preventDefault();
  const url = document.getElementById('stream-url').value.trim();
  const btn = document.getElementById('btn-submit');
  
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>Processing...</span>';
  }

  try {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        preset: selectedGenre,
        layout_mode: 'blur_bg',
        platform: 'instagram',
        target_clips: 4
      })
    });
    const data = await res.json();
    document.getElementById('stream-url').value = '';
    showToast(`Queued with ${selectedGenre.toUpperCase()} tuning (Job #${data.job_id})`, '🚀');
    fetchJobs();
  } catch (err) {
    showToast(`Queue failed: ${err.message}`, '❌');
  } finally {
    if (btn) {
      btn.disabled = false;
      const genreTag = document.getElementById('active-genre-tag');
      const label = genreTag ? genreTag.textContent.trim() : 'Clips';
      btn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        <span id="btn-submit-text">Generate ${label.split(' ')[1] || label} Clips</span>
      `;
    }
  }
}

let cachedJobs = [];
let selectedStreamFilter = 'all';
let previousJobStatuses = {};

function setupStreamFilterListener() {
  const filterSelect = document.getElementById('stream-filter-select');
  if (filterSelect && !filterSelect.dataset.listener) {
    filterSelect.dataset.listener = 'true';
    filterSelect.addEventListener('change', (e) => {
      selectedStreamFilter = e.target.value;
      renderJobsList(cachedJobs);
      if (selectedStreamFilter !== 'all') {
        const targetJob = cachedJobs.find(j => j.job_id === selectedStreamFilter);
        if (targetJob && targetJob.clips && targetJob.clips.length > 0) {
          selectClip(targetJob.job_id, targetJob.clips[0].clip_id);
        }
      }
    });
  }
}

async function fetchJobs() {
  try {
    const res = await fetch('/api/jobs');
    const jobs = await res.json();
    
    // Check for newly completed jobs to notify user and auto-select
    jobs.forEach(job => {
      const prev = previousJobStatuses[job.job_id];
      if (prev && prev !== 'completed' && job.status === 'completed' && job.clips && job.clips.length > 0) {
        showToast(`✨ Generated ${job.clips.length} highlights for "${job.title}"!`, '🎉');
        selectedStreamFilter = job.job_id;
      }
      previousJobStatuses[job.job_id] = job.status;
    });

    cachedJobs = jobs;
    setupStreamFilterListener();
    renderActiveJobsBanner(jobs);
    renderJobsList(jobs);
  } catch (err) {
    console.error('Fetch jobs error:', err);
  }
}

let activePollingInterval = null;

function renderActiveJobsBanner(jobs) {
  const banner = document.getElementById('active-jobs-banner');
  if (!banner) return;

  const inProgress = jobs.filter(j => j.status && j.status !== 'completed' && j.status !== 'failed');
  
  // Adaptive fast polling (every 1.5s) while background work is happening
  if (inProgress.length > 0 && !activePollingInterval) {
    activePollingInterval = setInterval(fetchJobs, 1500);
  } else if (inProgress.length === 0 && activePollingInterval) {
    clearInterval(activePollingInterval);
    activePollingInterval = null;
  }

  if (inProgress.length === 0) {
    banner.classList.add('hidden');
    banner.innerHTML = '';
    return;
  }

  banner.classList.remove('hidden');
  const stageLabels = {
    queued: '⏳ [1/4] In queue, initializing...',
    downloading: '⬇️ [1/4] Downloading source video stream...',
    transcribing: '🎙️ [2/4] Transcribing speech (Whisper on CUDA)...',
    analyzing: '🤖 [3/4] AI virality & hook scoring (Gemini)...',
    rendering: '⚡ [4/4] Rendering 9:16 clips (NVIDIA NVENC)...'
  };

  let html = '';
  inProgress.forEach(job => {
    const statusText = stageLabels[job.status] || `🔄 Processing (${job.status})...`;
    const pct = Math.max(5, Math.min(100, job.progress || 10));
    html += `
      <div class="processing-card">
        <div class="processing-header">
          <span class="processing-title" title="${escapeHtml(job.title || 'Video Stream')}">
            <span class="spin-icon">⚙️</span> ${escapeHtml(job.title || 'Processing Stream...')}
          </span>
          <span class="processing-status-tag">${pct}%</span>
        </div>
        <div class="processing-bar-wrapper">
          <div class="processing-bar-fill" style="width: ${pct}%;"></div>
        </div>
        <div class="processing-subtext">
          <span>${statusText}</span>
          <span>GPU Accelerated</span>
        </div>
      </div>
    `;
  });

  banner.innerHTML = html;
}

function renderJobsList(jobs) {
  const container = document.getElementById('jobs-list');
  const countBadge = document.getElementById('job-count');
  const filterSelect = document.getElementById('stream-filter-select');

  let allClips = [];
  // Deduplicate jobs by title for the stream selector, keeping newest
  const seenTitles = new Set();
  const validJobs = [];

  jobs.forEach(job => {
    if (job.clips && job.clips.length > 0) {
      job.clips.forEach(clip => {
        allClips.push({ ...clip, jobId: job.job_id, creator: job.creator, streamTitle: job.title });
      });
      if (!seenTitles.has(job.title)) {
        seenTitles.add(job.title);
        validJobs.push(job);
      }
    }
  });

  // Populate stream switcher options
  if (filterSelect) {
    const currentVal = selectedStreamFilter;
    let opts = `<option value="all">📁 All Video Highlights (${allClips.length})</option>`;
    validJobs.forEach(job => {
      const icon = (job.title || '').toLowerCase().includes('brighton') || (job.title || '').toLowerCase().includes('fulham') ? '⚽' : 
                   ((job.title || '').toLowerCase().includes('dream') ? '🎮' : '📺');
      opts += `<option value="${job.job_id}">${icon} ${escapeHtml(job.title)} (${job.clips.length})</option>`;
    });
    filterSelect.innerHTML = opts;
    if (validJobs.some(j => j.job_id === currentVal) || currentVal === 'all') {
      filterSelect.value = currentVal;
    } else {
      filterSelect.value = 'all';
      selectedStreamFilter = 'all';
    }
  }

  if (allClips.length === 0) {
    if (countBadge) countBadge.textContent = '0';
    if (filterSelect) filterSelect.innerHTML = '<option value="all">📁 No Streams Loaded (0)</option>';
    container.innerHTML = `
      <div class="empty-clips">
        <span>🎬</span>
        <p>No clips generated yet.<br>Paste a video link above and click Generate to start fresh.</p>
      </div>`;
    const video = document.getElementById('preview-video');
    if (video) {
      video.removeAttribute('src');
      video.load();
    }
    const titleEl = document.getElementById('active-clip-title');
    if (titleEl) titleEl.textContent = 'Clip Preview';
    const metaEl = document.getElementById('active-clip-meta');
    if (metaEl) metaEl.textContent = 'Paste a URL and choose a genre to begin';
    activeClip = null;
    activeJobId = null;
    return;
  }

  const visibleClips = (selectedStreamFilter === 'all')
    ? allClips
    : allClips.filter(c => c.jobId === selectedStreamFilter);

  if (countBadge) countBadge.textContent = `${visibleClips.length}`;

  if (visibleClips.length === 0) {
    container.innerHTML = `
      <div class="empty-clips">
        <span>🎬</span>
        <p>No clips found for this video. Select another stream above.</p>
      </div>`;
    return;
  }

  let html = '';
  visibleClips.forEach((clip, idx) => {
    const isSelected = activeClip && activeClip.clip_id === clip.clip_id;
    const score = clip.virality_score || 90;
    const dur = Math.round(clip.duration || 35);
    const streamTag = (clip.streamTitle || '').split('|')[0].split('·')[0].trim();

    html += `
      <div class="clip-card ${isSelected ? 'active' : ''}" onclick="selectClip('${clip.jobId}', '${clip.clip_id}')">
        <div class="clip-card-header">
          <span class="clip-card-badge">🔥 ${score}% virality</span>
          <span class="clip-card-duration">0:${dur < 10 ? '0' : ''}${dur}</span>
        </div>
        <div class="clip-card-title">${escapeHtml(clip.title || `Clip #${idx + 1}`)}</div>
        <div class="clip-card-footer">
          <span>@${escapeHtml((clip.creator || 'streamer').toLowerCase().replace(/\s+/g, ''))}</span>
          <span class="clip-source-pill" title="${escapeHtml(clip.streamTitle || '')}">${escapeHtml(streamTag)}</span>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;

  // Auto-select first clip if none selected or if active clip not in current view
  if (visibleClips.length > 0) {
    const isCurrentActiveVisible = activeClip && visibleClips.some(c => c.clip_id === activeClip.clip_id);
    if (!activeClip || !isCurrentActiveVisible) {
      selectClip(visibleClips[0].jobId, visibleClips[0].clip_id);
    }
  }
}

window.selectClip = async function(jobId, clipId) {
  activeJobId = jobId;
  try {
    let job = cachedJobs.find(j => j.job_id === jobId);
    if (!job) {
      const res = await fetch(`/api/jobs/${jobId}`);
      job = await res.json();
    }
    const clip = job.clips.find(c => c.clip_id === clipId);
    if (!clip) return;

    activeClip = clip;

    // Video Element
    const video = document.getElementById('preview-video');
    if (video) {
      video.src = clip.video_url;
      video.load();
      video.play().catch(() => {});
    }

    // Header metadata
    const titleEl = document.getElementById('active-clip-title');
    if (titleEl) titleEl.textContent = clip.title || 'Clip Preview';

    const metaEl = document.getElementById('active-clip-meta');
    if (metaEl) {
      metaEl.textContent = `${job.title} · @${(job.creator || 'streamer').toLowerCase().replace(/\s+/g, '')} · ${clip.duration}s`;
    }

    // Virality score
    const scoreVal = document.getElementById('score-val');
    if (scoreVal) scoreVal.textContent = clip.virality_score || '95';

    // Trimmer values
    const startInput = document.getElementById('trim-start');
    const endInput = document.getElementById('trim-end');
    if (startInput) startInput.value = clip.start_time;
    if (endInput) endInput.value = clip.end_time;
    updateDurationDisplay();

    // Layout & Platform Selectors
    const layoutSelect = document.getElementById('edit-layout-mode');
    if (layoutSelect) layoutSelect.value = clip.layout_mode || 'blur_bg';

    const platformSelect = document.getElementById('edit-platform');
    if (platformSelect) platformSelect.value = clip.platform || 'instagram';

    // Strategy & Captions
    const strategyText = document.getElementById('ai-strategy-text');
    if (strategyText) {
      strategyText.textContent = clip.reason || 'High emotional engagement and dynamic dialogue flow.';
    }

    const titleInput = document.getElementById('meta-title');
    if (titleInput) titleInput.value = clip.title || '';

    const captionInput = document.getElementById('meta-caption');
    if (captionInput) {
      const hashtags = (clip.hashtags || []).join(' ');
      captionInput.value = `${clip.description || ''}\n\n${hashtags}`;
    }

    // Update active highlight in sidebar
    document.querySelectorAll('.clip-card').forEach(card => {
      card.classList.remove('active');
    });
  } catch (err) {
    console.error('Error selecting clip:', err);
  }
};

window.adjustTime = function(type, delta) {
  const input = document.getElementById(`trim-${type}`);
  if (!input) return;
  let val = parseFloat(input.value) || 0;
  val = Math.max(0, parseFloat((val + delta).toFixed(1)));
  input.value = val;
  updateDurationDisplay();
};

function updateDurationDisplay() {
  const start = parseFloat(document.getElementById('trim-start')?.value) || 0;
  const end = parseFloat(document.getElementById('trim-end')?.value) || 0;
  const dur = Math.max(0, (end - start).toFixed(1));

  const durText = document.getElementById('clip-duration-text');
  if (durText) durText.textContent = `${dur}s`;

  const statusPill = document.getElementById('duration-status-pill');
  if (statusPill) {
    if (dur >= 20 && dur <= 45) {
      statusPill.textContent = 'Optimal (25-45s)';
      statusPill.style.color = '#34d399';
    } else if (dur > 45 && dur <= 60) {
      statusPill.textContent = 'Good (Loopable)';
      statusPill.style.color = '#fbbf24';
    } else {
      statusPill.textContent = 'Long (>60s)';
      statusPill.style.color = '#f87171';
    }
  }
}

async function handleReRender() {
  if (!activeClip) return;

  const btn = document.getElementById('btn-re-render');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Rendering (NVENC)...';
  }

  const start = parseFloat(document.getElementById('trim-start').value);
  const end = parseFloat(document.getElementById('trim-end').value);
  const layout = document.getElementById('edit-layout-mode').value;
  const platform = document.getElementById('edit-platform').value;

  const checkedColor = document.querySelector('input[name="subtitle_color"]:checked');
  const subColor = checkedColor ? checkedColor.value : '&H00FFFF&';

  try {
    const res = await fetch(`/api/clips/${activeClip.clip_id}/fine_tune`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_time: start,
        end_time: end,
        layout_mode: layout,
        platform: platform,
        highlight_color: subColor,
        subtitles_enabled: true
      })
    });
    const data = await res.json();
    if (data.clip) {
      activeClip = data.clip;
      const video = document.getElementById('preview-video');
      if (video) {
        video.src = data.clip.video_url;
        video.load();
        video.play();
      }
      showToast('Re-rendered with NVENC hardware acceleration', '✓');
    }
  } catch (err) {
    showToast('Re-render error: ' + err.message, '❌');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔄 Apply & Re-render (NVENC Accelerated)';
    }
  }
}

async function handleExport() {
  if (!activeClip) return;
  const btn = document.getElementById('btn-download-mp4');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Preparing download...';
  }

  try {
    const res = await fetch(`/api/clips/${activeClip.clip_id}/export`, {
      method: 'POST'
    });
    const data = await res.json();
    if (data.export_url) {
      const a = document.createElement('a');
      a.href = data.export_url;
      a.download = data.file_name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      showToast(`Downloaded ${data.file_name}`, '⬇️');
    }
  } catch (err) {
    showToast('Export error: ' + err.message, '❌');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        <span>Download 1080x1920 MP4 (Instagram Ready)</span>
      `;
    }
  }
}

window.copyText = function(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.select();
  navigator.clipboard.writeText(el.value);
  showToast('Copied to clipboard', '✓');
};

function showToast(message, icon = '✓') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 250);
  }, 2400);
}

function escapeHtml(text) {
  if (!text) return '';
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
