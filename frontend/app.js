let activeJobId = null;
let activeClip = null;
let systemProfiles = {};

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

async function initApp() {
  await fetchSystemStatus();
  fetchJobs();
  setupEventListeners();

  // Poll jobs list periodically
  setInterval(fetchJobs, 3500);
}

function setupEventListeners() {
  // Ingest form submission
  const form = document.getElementById('ingest-form');
  form.addEventListener('submit', handleIngestSubmit);

  // Paste button
  const pasteBtn = document.getElementById('btn-paste');
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
      showToast('Gemini API key saved & connected', '🔑');
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
    const dur = Math.floor(video.duration || 0);
    const dm = Math.floor(dur / 60);
    const ds = dur % 60;
    document.getElementById('player-time-badge').textContent = 
      `${m}:${s < 10 ? '0' : ''}${s} / ${dm}:${ds < 10 ? '0' : ''}${ds}`;
  });

  // Trim inputs change listener
  ['trim-start', 'trim-end'].forEach(id => {
    document.getElementById(id).addEventListener('input', updateDurationDisplay);
  });

  // Instagram Overlay Toggle
  const toggleOverlayBtn = document.getElementById('btn-toggle-overlay');
  if (toggleOverlayBtn) {
    toggleOverlayBtn.addEventListener('click', () => {
      const overlay = document.getElementById('instagram-overlay');
      const isHidden = overlay.classList.contains('hidden');
      if (isHidden) {
        overlay.classList.remove('hidden');
        toggleOverlayBtn.classList.add('active');
        document.getElementById('toggle-overlay-text').textContent = 'Hide Instagram Safe-Zone';
        showToast('Instagram Reels UI safe-zone enabled', '👁️');
      } else {
        overlay.classList.add('hidden');
        toggleOverlayBtn.classList.remove('active');
        document.getElementById('toggle-overlay-text').textContent = 'Show Instagram UI Safe-Zone';
      }
    });
  }

  // Edit Platform Change Listener
  const editPlatformSelect = document.getElementById('edit-platform');
  if (editPlatformSelect) {
    editPlatformSelect.addEventListener('change', () => {
      const selected = editPlatformSelect.value;
      updateSpecPill(selected);
    });
  }

  // Ingest Platform Radio Change Listener
  document.querySelectorAll('input[name="platform_preset"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      updateSpecPill(e.target.value);
    });
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
      badge.textContent = `⚡ RTX 3080 (${data.encoder})`;
      if (encoderSpan) encoderSpan.textContent = `NVIDIA NVENC (${data.encoder}) Hardware Accelerated`;
    } else {
      badge.textContent = 'CPU Mode';
      if (encoderSpan) encoderSpan.textContent = 'CPU (libx264)';
    }

    // Default platform badge
    updateSpecPill('instagram');
  } catch (err) {
    console.error('Status fetch error:', err);
  }
}

function updateSpecPill(platform) {
  const specText = document.getElementById('spec-text');
  const playerSpec = document.getElementById('player-spec-badge');
  const settingsPlatform = document.getElementById('settings-platform');

  if (platform === 'instagram') {
    if (specText) specText.textContent = 'Instagram Reels · 4.5M H.264 · 30fps · BT.709';
    if (playerSpec) playerSpec.textContent = '4.5M Reels H.264';
    if (settingsPlatform) settingsPlatform.textContent = 'Instagram Reels (4.5M H.264 High · BT.709)';
  } else if (platform === 'tiktok') {
    if (specText) specText.textContent = 'TikTok · 5.5M H.264 · 30fps';
    if (playerSpec) playerSpec.textContent = '5.5M TikTok';
    if (settingsPlatform) settingsPlatform.textContent = 'TikTok (5.5M H.264 Standard)';
  } else {
    if (specText) specText.textContent = 'YouTube Shorts · 8.0M HQ · 30fps';
    if (playerSpec) playerSpec.textContent = '8.0M Shorts HQ';
    if (settingsPlatform) settingsPlatform.textContent = 'YouTube Shorts (8.0M HQ)';
  }
}

async function handleIngestSubmit(e) {
  e.preventDefault();
  const url = document.getElementById('stream-url').value.trim();
  const targetClips = parseInt(document.getElementById('target-clips').value, 10);
  const layoutMode = document.querySelector('input[name="layout_mode"]:checked').value;
  const platformPreset = document.querySelector('input[name="platform_preset"]:checked').value;
  const contentPreset = document.querySelector('input[name="content_preset"]:checked') 
    ? document.querySelector('input[name="content_preset"]:checked').value 
    : 'streamer';

  const btn = document.getElementById('btn-submit');
  btn.disabled = true;
  btn.innerHTML = '<span class="pulse-dot"></span><span>Queueing AI Stream Pipeline...</span>';

  try {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        preset: contentPreset,
        layout_mode: layoutMode,
        platform: platformPreset,
        target_clips: targetClips
      })
    });
    const data = await res.json();
    document.getElementById('stream-url').value = '';
    showToast(`Stream queued (Job #${data.job_id})`, '🚀');
    fetchJobs();
  } catch (err) {
    showToast(`Failed to queue job: ${err.message}`, '❌');
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
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📺</div>
        <p>No streams processed yet. Paste a stream URL above to start automated clipping.</p>
      </div>`;
    return;
  }

  let html = '';
  const sortedJobs = [...jobs].reverse();

  sortedJobs.forEach(job => {
    const isActive = activeJobId === job.job_id;
    const statusClass = `status-${job.status}`;

    let clipPills = '';
    if (job.clips && job.clips.length > 0) {
      clipPills = '<div class="job-clip-pills">';
      job.clips.forEach((clip, idx) => {
        const isSelected = activeClip && activeClip.clip_id === clip.clip_id;
        const hookTag = clip.hook_type ? ` · ${clip.hook_type.split(' ')[0]}` : '';
        clipPills += `
          <button class="clip-pill ${isSelected ? 'active' : ''}" onclick="selectClip('${job.job_id}', '${clip.clip_id}')">
            🔥 #${idx + 1} (${clip.virality_score}%${hookTag})
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
    document.getElementById('active-clip-meta').textContent = 
      `${job.creator || 'Streamer'} · ${clip.duration}s · Optimized for ${clip.platform || 'Instagram Reels'}`;
    
    // Virality score
    const viralityTag = document.getElementById('virality-score-tag');
    viralityTag.classList.remove('hidden');
    document.getElementById('score-val').textContent = clip.virality_score || '90';

    // Hook type and retention pills
    const hookTypeTag = document.getElementById('hook-type-tag');
    if (hookTypeTag) {
      hookTypeTag.textContent = `🎯 ${clip.hook_type || 'Curiosity Gap'}`;
      hookTypeTag.classList.remove('hidden');
    }

    const retentionTag = document.getElementById('retention-score-tag');
    if (retentionTag) {
      retentionTag.textContent = `⚡ ${clip.retention_prediction || clip.virality_score || 88}% Retention`;
      retentionTag.classList.remove('hidden');
    }

    // Video badges
    document.getElementById('player-layout-badge').textContent = 
      clip.layout_mode === 'split_screen' ? 'Split Screen' : (clip.layout_mode === 'smart_crop' ? 'Face Tracking' : 'Blur BG');

    const currentPlatform = clip.platform || 'instagram';
    updateSpecPill(currentPlatform);

    // Populate Trimmer
    document.getElementById('trim-start').value = clip.start_time;
    document.getElementById('trim-end').value = clip.end_time;
    updateDurationDisplay();

    // Layout & Platform Selectors
    document.getElementById('edit-layout-mode').value = clip.layout_mode || 'blur_bg';
    if (document.getElementById('edit-platform')) {
      document.getElementById('edit-platform').value = currentPlatform;
    }

    // Strategy breakdown
    const strategyText = document.getElementById('ai-strategy-text');
    if (strategyText) {
      strategyText.textContent = clip.reason || 'High emotional engagement and dynamic dialogue flow with detected volume peaks.';
    }

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

  const statusPill = document.getElementById('duration-status-pill');
  if (statusPill) {
    if (dur >= 20 && dur <= 45) {
      statusPill.textContent = '✓ Optimal for Reels & Loopability';
      statusPill.className = 'pill-duration-good';
      statusPill.style.color = '#34d399';
    } else if (dur > 45 && dur <= 60) {
      statusPill.textContent = '⚡ Good pacing (Slightly long for loops)';
      statusPill.style.color = '#fbbf24';
    } else {
      statusPill.textContent = '⚠️ Attention: Over 60s will not monetize on Shorts';
      statusPill.style.color = '#f87171';
    }
  }
}

async function handleReRender() {
  if (!activeClip) return;

  const btn = document.getElementById('btn-re-render');
  btn.disabled = true;
  btn.textContent = '⏳ Rendering NVENC Preview (4.5M H.264)...';

  const start = parseFloat(document.getElementById('trim-start').value);
  const end = parseFloat(document.getElementById('trim-end').value);
  const layout = document.getElementById('edit-layout-mode').value;
  const platform = document.getElementById('edit-platform') ? document.getElementById('edit-platform').value : 'instagram';
  
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
      video.src = data.clip.video_url;
      video.load();
      video.play();
      document.getElementById('player-layout-badge').textContent = 
        layout === 'split_screen' ? 'Split Screen' : (layout === 'smart_crop' ? 'Face Tracking' : 'Blur BG');
      updateSpecPill(platform);
      showToast('Re-rendered with Instagram-optimal bitrate & safe margins', '✓');
    }
  } catch (err) {
    showToast('Re-render failed: ' + err.message, '❌');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 Apply Adjustments & Re-render (NVENC Accelerated)';
  }
}

async function handleExport() {
  if (!activeClip) return;
  const btn = document.getElementById('btn-download-mp4');
  btn.disabled = true;
  btn.textContent = 'Preparing Final 1080x1920 MP4...';

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
    btn.disabled = false;
    btn.textContent = '⬇️ Download Final 1080x1920 MP4 (Instagram Ready)';
  }
}

window.copyText = function(elementId) {
  const el = document.getElementById(elementId);
  el.select();
  navigator.clipboard.writeText(el.value);
  
  const label = elementId === 'meta-title' ? 'Viral Title' : 'Caption & Hashtags';
  showToast(`Copied ${label} for Instagram upload`, '✓');

  const copyBtn = el.previousElementSibling ? el.previousElementSibling.querySelector('.btn-copy') : null;
  if (copyBtn) {
    const prevText = copyBtn.textContent;
    copyBtn.textContent = '✓ Copied!';
    setTimeout(() => { copyBtn.textContent = prevText; }, 1800);
  }
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
  }, 2600);
}

function escapeHtml(text) {
  if (!text) return '';
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
