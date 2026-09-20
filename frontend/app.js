let activeJobId = null;
let activeClip = null;
let pollingInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

async function initApp() {
  fetchSystemStatus();
  fetchJobs();
  setupEventListeners();

  // Poll jobs list periodically
  setInterval(fetchJobs, 4000);
}

function setupEventListeners() {
  // Ingest form
  const form = document.getElementById('ingest-form');
  form.addEventListener('submit', handleIngestSubmit);

  // Paste button
  const pasteBtn = document.getElementById('btn-paste');
  pasteBtn.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        document.getElementById('stream-url').value = text;
      }
    } catch (err) {
      console.warn('Clipboard read failed:', err);
    }
  });

  // Settings Modal
  const settingsBtn = document.getElementById('btn-settings');
  const modal = document.getElementById('settings-modal');
  const closeBtn = document.getElementById('btn-close-modal');
  const saveSettingsBtn = document.getElementById('btn-save-settings');

  settingsBtn.addEventListener('click', () => {
    modal.classList.remove('hidden');
  });

  closeBtn.addEventListener('click', () => {
    modal.classList.add('hidden');
  });

  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.add('hidden');
  });

  saveSettingsBtn.addEventListener('click', async () => {
    const key = document.getElementById('modal-gemini-key').value.trim();
    if (key) {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gemini_api_key: key })
      });
    }
    modal.classList.add('hidden');
    fetchSystemStatus();
  });

  // Fine-tuning re-render
  document.getElementById('btn-re-render').addEventListener('click', handleReRender);

  // Export / Download
  document.getElementById('btn-download-mp4').addEventListener('click', handleExport);

  // Video time update badge
  const video = document.getElementById('preview-video');
  video.addEventListener('timeupdate', () => {
    const curr = Math.floor(video.currentTime);
    const m = Math.floor(curr / 60);
    const s = curr % 60;
    document.getElementById('player-time-badge').textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
  });

  // Trim inputs change listener
  ['trim-start', 'trim-end'].forEach(id => {
    document.getElementById(id).addEventListener('input', updateDurationDisplay);
  });
}

async function fetchSystemStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const badge = document.getElementById('gpu-text');
    const encoderSpan = document.getElementById('settings-encoder');

    if (data.cuda_available) {
      badge.textContent = `⚡ RTX 3080 (${data.encoder})`;
      if (encoderSpan) encoderSpan.textContent = `NVIDIA NVENC (${data.encoder})`;
    } else {
      badge.textContent = 'CPU Mode';
      if (encoderSpan) encoderSpan.textContent = 'CPU (libx264)';
    }
  } catch (err) {
    console.error('Status fetch error:', err);
  }
}

async function handleIngestSubmit(e) {
  e.preventDefault();
  const url = document.getElementById('stream-url').value.trim();
  const targetClips = parseInt(document.getElementById('target-clips').value, 10);
  const layoutMode = document.querySelector('input[name="layout_mode"]:checked').value;

  const btn = document.getElementById('btn-submit');
  btn.disabled = true;
  btn.innerHTML = '<span>Queueing Stream...</span>';

  try {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        layout_mode: layoutMode,
        target_clips: targetClips
      })
    });
    const data = await res.json();
    document.getElementById('stream-url').value = '';
    fetchJobs();
  } catch (err) {
    alert('Failed to queue job: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg><span>Extract Viral Clips</span>';
  }
}

async function fetchJobs() {
  try {
    const res = await fetch('/api/jobs');
    const jobs = await res.json();
    renderJobsList(jobs);
  } catch (err) {
    console.error('Fetch jobs error:', err);
  }
}

function renderJobsList(jobs) {
  const container = document.getElementById('jobs-list');
  const countBadge = document.getElementById('job-count');
  countBadge.textContent = `${jobs.length} jobs`;

  if (jobs.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>No streams processed yet. Paste a URL above to start automated clipping.</p></div>';
    return;
  }

  // Preserve current HTML if status and progress didn't change
  let html = '';
  // Reverse to show latest first
  const sortedJobs = [...jobs].reverse();

  sortedJobs.forEach(job => {
    const isActive = activeJobId === job.job_id;
    const statusClass = `status-${job.status}`;

    let clipPills = '';
    if (job.clips && job.clips.length > 0) {
      clipPills = '<div class="job-clip-pills">';
      job.clips.forEach((clip, idx) => {
        const isSelected = activeClip && activeClip.clip_id === clip.clip_id;
        clipPills += `
          <button class="clip-pill ${isSelected ? 'active' : ''}" onclick="selectClip('${job.job_id}', '${clip.clip_id}')">
            🔥 #${idx + 1} (${clip.virality_score}%)
          </button>
        `;
      });
      clipPills += '</div>';
    }

    html += `
      <div class="job-card ${isActive ? 'active' : ''}">
        <div class="job-header">
          <div class="job-title">${escapeHtml(job.title)}</div>
          <span class="job-status-pill ${statusClass}">${job.status}</span>
        </div>
        <div class="job-progress-bar">
          <div class="job-progress-fill" style="width: ${job.progress || 10}%"></div>
        </div>
        ${clipPills}
      </div>
    `;
  });

  container.innerHTML = html;

  // Auto-select first clip of finished job if none selected
  if (!activeClip && jobs.length > 0) {
    const latestWithClips = sortedJobs.find(j => j.clips && j.clips.length > 0);
    if (latestWithClips) {
      selectClip(latestWithClips.job_id, latestWithClips.clips[0].clip_id);
    }
  }
}

window.selectClip = async function(jobId, clipId) {
  activeJobId = jobId;
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    const job = await res.json();
    const clip = job.clips.find(c => c.clip_id === clipId);
    if (!clip) return;

    activeClip = clip;

    // Show curation deck
    document.getElementById('curation-placeholder').classList.add('hidden');
    document.getElementById('curation-content').classList.remove('hidden');

    // Populate video
    const video = document.getElementById('preview-video');
    video.src = clip.video_url;
    video.load();

    // Populate titles & badges
    document.getElementById('active-clip-title').textContent = clip.title || 'Clip Review';
    document.getElementById('active-clip-meta').textContent = `${job.creator || 'Streamer'} · Original duration: ${clip.duration}s`;
    
    const viralityTag = document.getElementById('virality-score-tag');
    viralityTag.classList.remove('hidden');
    document.getElementById('score-val').textContent = clip.virality_score || '90';

    document.getElementById('player-layout-badge').textContent = clip.layout_mode || 'Blur BG';

    // Populate Trimmer
    document.getElementById('trim-start').value = clip.start_time;
    document.getElementById('trim-end').value = clip.end_time;
    updateDurationDisplay();

    // Layout
    document.getElementById('edit-layout-mode').value = clip.layout_mode || 'blur_bg';

    // Metadata
    document.getElementById('meta-title').value = clip.title || '';
    const hashtags = (clip.hashtags || []).join(' ');
    document.getElementById('meta-caption').value = `${clip.description || ''}\n\n${hashtags}`;

    fetchJobs(); // Update active highlights
  } catch (err) {
    console.error('Error selecting clip:', err);
  }
};

window.adjustTime = function(type, delta) {
  const input = document.getElementById(`trim-${type}`);
  let val = parseFloat(input.value) || 0;
  val = Math.max(0, parseFloat((val + delta).toFixed(1)));
  input.value = val;
  updateDurationDisplay();
};

function updateDurationDisplay() {
  const start = parseFloat(document.getElementById('trim-start').value) || 0;
  const end = parseFloat(document.getElementById('trim-end').value) || 0;
  const dur = Math.max(0, (end - start).toFixed(1));
  document.getElementById('clip-duration-text').textContent = `${dur}s`;
}

async function handleReRender() {
  if (!activeClip) return;

  const btn = document.getElementById('btn-re-render');
  btn.disabled = true;
  btn.textContent = '⏳ Rendering GPU Preview...';

  const start = parseFloat(document.getElementById('trim-start').value);
  const end = parseFloat(document.getElementById('trim-end').value);
  const layout = document.getElementById('edit-layout-mode').value;
  const subColor = document.getElementById('edit-subtitle-color').value;

  try {
    const res = await fetch(`/api/clips/${activeClip.clip_id}/fine_tune`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_time: start,
        end_time: end,
        layout_mode: layout,
        highlight_color: subColor,
        subtitles_enabled: true
      })
    });
    const data = await res.json();
    if (data.clip) {
      activeClip = data.clip;
      const video = document.getElementById('preview-video');
      video.src = data.clip.video_url;
      video.load();
      video.play();
      document.getElementById('player-layout-badge').textContent = layout;
    }
  } catch (err) {
    alert('Re-render failed: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 Apply Adjustments & Re-render Preview';
  }
}

async function handleExport() {
  if (!activeClip) return;
  const btn = document.getElementById('btn-download-mp4');
  btn.disabled = true;
  btn.textContent = 'Preparing Download...';

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
    }
  } catch (err) {
    alert('Export error: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '⬇️ Download Final 1080x1920 MP4';
  }
}

window.copyText = function(elementId) {
  const el = document.getElementById(elementId);
  el.select();
  navigator.clipboard.writeText(el.value);
  
  const originalVal = el.value;
  const copyBtn = el.previousElementSibling ? el.previousElementSibling.querySelector('.btn-copy') : null;
  if (copyBtn) {
    const prevText = copyBtn.textContent;
    copyBtn.textContent = '✓ Copied!';
    setTimeout(() => { copyBtn.textContent = prevText; }, 1500);
  }
};

function escapeHtml(text) {
  if (!text) return '';
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
