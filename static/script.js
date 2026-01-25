const processedTasks = new Map(); // filename -> taskId
const manualScripts = new Map(); // filename -> text
let currentScriptFilename = null;

// Pagination State
let allVideos = [];
let currentPage = 1;
const ITEMS_PER_PAGE = 10;

document.addEventListener('DOMContentLoaded', () => {
  fetchVideos();

  document.getElementById('refreshBtn').addEventListener('click', fetchVideos);
  document
    .getElementById('processAllBtn')
    .addEventListener('click', processAll);
  document
    .getElementById('downloadAllBtn')
    .addEventListener('click', downloadAll);

  // Engine Toggle
  const engineSelect = document.getElementById('translationEngine');
  if (engineSelect) {
    engineSelect.addEventListener('change', toggleEngine);
    toggleEngine();
  }

  // Modal Close - Fix for multiple modals
  document.querySelectorAll('.close-modal').forEach((btn) => {
    btn.addEventListener('click', () => {
      closeModal();
      closeScriptModal();
    });
  });

  const closeScriptBtn = document.getElementById('closeScriptBtn');
  if (closeScriptBtn)
    closeScriptBtn.addEventListener('click', closeScriptModal);

  const cancelScriptBtn = document.getElementById('cancelScriptBtn');
  if (cancelScriptBtn)
    cancelScriptBtn.addEventListener('click', closeScriptModal);

  const saveScriptBtn = document.getElementById('saveScriptBtn');
  if (saveScriptBtn) saveScriptBtn.addEventListener('click', saveScript);

  window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
      closeModal();
      closeScriptModal();
    }
  });
});

async function toggleEngine() {
  const engine = document.getElementById('translationEngine').value;
  const ollamaGroup = document.getElementById('ollamaGroup');
  const geminiGroup = document.getElementById('geminiGroup');

  // Hide all engine-specific groups first
  ollamaGroup.classList.add('hidden');
  geminiGroup.classList.add('hidden');

  if (engine === 'ollama') {
    ollamaGroup.classList.remove('hidden');
    await fetchOllamaModels();
  } else if (engine === 'gemini') {
    geminiGroup.classList.remove('hidden');
    // Load saved API key from localStorage
    const savedKey = localStorage.getItem('geminiApiKey');
    if (savedKey) {
      document.getElementById('geminiApiKey').value = savedKey;
    }
    // Check Gemini status
    await checkGeminiStatus();
  }
}

// Gemini API key functions
function toggleApiKeyVisibility() {
  const input = document.getElementById('geminiApiKey');
  input.type = input.type === 'password' ? 'text' : 'password';
}

async function testGeminiKey() {
  const btn = document.getElementById('testGeminiBtn');
  const input = document.getElementById('geminiApiKey');
  const apiKey = input.value.trim();

  if (!apiKey) {
    alert('Please enter an API key');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Testing...';

  try {
    const res = await fetch('/api/gemini/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = await res.json();

    if (data.success) {
      btn.textContent = '✓ Valid';
      btn.classList.add('btn-success');
      // Save to localStorage
      localStorage.setItem('geminiApiKey', apiKey);
      setTimeout(() => {
        btn.textContent = 'Test';
        btn.classList.remove('btn-success');
      }, 2000);
    } else {
      btn.textContent = '✗ Failed';
      alert('API key test failed: ' + (data.error || 'Unknown error'));
      setTimeout(() => {
        btn.textContent = 'Test';
      }, 2000);
    }
  } catch (err) {
    console.error('Gemini test error', err);
    btn.textContent = '✗ Error';
    setTimeout(() => {
      btn.textContent = 'Test';
    }, 2000);
  } finally {
    btn.disabled = false;
  }
}

async function checkGeminiStatus() {
  try {
    const res = await fetch('/api/gemini/status');
    const data = await res.json();

    if (!data.available) {
      const group = document.getElementById('geminiGroup');
      const note = document.createElement('small');
      note.style.color = '#f55';
      note.textContent =
        '⚠ Gemini unavailable. Check console logs. Missing deep-translator?';
      group.appendChild(note);
    }
  } catch (err) {
    console.error('Gemini status check failed', err);
  }
}

async function fetchOllamaModels() {
  const select = document.getElementById('ollamaModel');
  if (select.options.length > 1) return;

  try {
    select.innerHTML = '<option>Loading...</option>';
    const res = await fetch('/api/ollama/models');
    const data = await res.json();

    select.innerHTML = '';

    if (data.models && data.models.length > 0) {
      data.models.forEach((model) => {
        const opt = document.createElement('option');
        opt.value = model.name;
        // Show ⭐ for recommended models
        opt.textContent = model.recommended ? `⭐ ${model.name}` : model.name;
        select.appendChild(opt);
      });

      // Auto-select first recommended model
      const recommended = data.models.find((m) => m.recommended);
      if (recommended) {
        select.value = recommended.name;
      }
    } else {
      select.innerHTML =
        '<option value="">No text models found - use Google Translate</option>';
    }
  } catch (err) {
    console.error('Ollama fetch failed', err);
    select.innerHTML =
      '<option value="">Ollama not running - use Google Translate</option>';
  }
}

async function fetchVideos() {
  try {
    const res = await fetch('/api/videos');
    allVideos = await res.json();
    currentPage = 1; // Reset to first page on refresh
    renderPage();
  } catch (err) {
    console.error('Failed to fetch videos', err);
  }
}

function renderPage() {
  const totalPages = Math.ceil(allVideos.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const pageVideos = allVideos.slice(startIndex, endIndex);
  
  renderTable(pageVideos, startIndex);
  renderPagination(totalPages);
}

function renderTable(videos, startIndexOffset = 0) {
  const tbody = document.getElementById('videoTableBody');
  tbody.innerHTML = '';

  videos.forEach((video, index) => {
    const globalIndex = startIndexOffset + index;
    // 1. Pre-load script content if available from server (and not already manually edited in session)
    if (video.srt_content && !manualScripts.has(video.name)) {
        manualScripts.set(video.name, video.srt_content);
    }

    const row = document.createElement('tr');
    row.dataset.filename = video.name;

    const suggestedName = video.name.replace('.mp4', '_subtitled.mp4');
    
    // Determine Script Button State
    const hasScript = manualScripts.has(video.name) || video.has_srt;
    const scriptBtnClass = hasScript ? 'btn-success' : 'secondary';
    const scriptBtnText = hasScript ? '📝 Edit' : '➕ Add';

    // Determine Status & Actions State
    let statusClass = 'idle';
    let statusText = 'Idle';
    let showResults = false;
    let downloadUrl = '#';
    let processBtnText = 'Process';
    let processBtnDisabled = false;

    if (video.has_output) {
        statusClass = 'done';
        statusText = 'Done';
        showResults = true;
        downloadUrl = `/videos/output/${video.output_file}`;
        processBtnText = 'Redo';
    } else if (video.has_srt) {
        statusClass = 'queued'; // Or a new class for 'Ready'/'Transcribed'? Re-using queued for visibility or create new 'info'
        statusText = 'Transcribed';
        // Allow processing to continue to Dubbing/Burning
    }
    
    // Helper to hide/show
    const resultHiddenClass = showResults ? '' : 'hidden';
    
    // Preview button - show result if available, otherwise input
    const previewType = video.has_output ? 'output' : 'input';
    const previewFile = video.has_output ? video.output_file : video.name;
    const previewIcon = video.has_output ? '✅' : '▶️';
    const previewTitle = video.has_output ? 'Preview Result' : 'Preview Original';

    row.innerHTML = `
            <td class="col-mini">
                <button class="icon-btn preview-btn" title="${previewTitle}" onclick="previewVideo('${previewType}', '${previewFile}')">${previewIcon}</button>
            </td>
            <td>${video.name}</td>
            <td class="col-wide">
                <input type="text" class="rename-input" value="${suggestedName}" placeholder="Output filename...">
            </td>
            <td style="text-align: center;">
                 <input type="checkbox" class="dub-check" title="Enable Dubbing">
            </td>
            <td style="text-align: center;">
                <button class="btn ${scriptBtnClass} btn-small" onclick="openScriptModal('${video.name}')">${scriptBtnText}</button>
            </td>
            <td class="metrics-cell">
                <div class="metric-duration">-</div>
                <div class="metric-progress">0%</div>
            </td>
            <td class="col-status">
                <span class="badge ${statusClass}" id="status-${index}">${statusText}</span>
            </td>
            <td class="col-actions">
                <div class="action-cell">
                    <button class="btn primary btn-small process-btn" onclick="startProcess('${video.name}')" ${processBtnDisabled ? 'disabled' : ''}>${processBtnText}</button>
                    <button class="btn secondary btn-small reset-btn" onclick="resetRow('${video.name}')" title="Reset / Delete Artifacts">🔄</button>
                    <!-- Result Actions -->
                    <button class="btn-icon watch ${resultHiddenClass}" title="Watch Result" onclick="previewVideo('output', '${video.output_file}')">👀</button>
                    <a href="${downloadUrl}" class="btn-icon download-link ${resultHiddenClass}" title="Download" target="_blank">⬇</a>
                </div>
            </td>
        `;
    tbody.appendChild(row);
  });
}

function renderPagination(totalPages) {
  let paginationContainer = document.getElementById('paginationContainer');
  
  // Create container if it doesn't exist
  if (!paginationContainer) {
    paginationContainer = document.createElement('div');
    paginationContainer.id = 'paginationContainer';
    paginationContainer.className = 'pagination';
    const tableContainer = document.querySelector('.table-container');
    tableContainer.parentNode.insertBefore(paginationContainer, tableContainer.nextSibling);
  }
  
  // Don't show pagination if only 1 page
  if (totalPages <= 1) {
    paginationContainer.innerHTML = '';
    return;
  }
  
  let html = '';
  
  // Previous Button
  html += `<button class="page-btn ${currentPage === 1 ? 'disabled' : ''}" onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>← Prev</button>`;
  
  // Page Numbers
  for (let i = 1; i <= totalPages; i++) {
    if (i === currentPage) {
      html += `<button class="page-btn active">${i}</button>`;
    } else if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
      // Show first, last, and nearby pages
      html += `<button class="page-btn" onclick="goToPage(${i})">${i}</button>`;
    } else if (i === currentPage - 3 || i === currentPage + 3) {
      // Ellipsis
      html += `<span class="page-ellipsis">...</span>`;
    }
  }
  
  // Next Button
  html += `<button class="page-btn ${currentPage === totalPages ? 'disabled' : ''}" onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>Next →</button>`;
  
  // Page Info
  const startItem = (currentPage - 1) * ITEMS_PER_PAGE + 1;
  const endItem = Math.min(currentPage * ITEMS_PER_PAGE, allVideos.length);
  html += `<span class="page-info">Showing ${startItem}-${endItem} of ${allVideos.length}</span>`;
  
  paginationContainer.innerHTML = html;
}

function goToPage(page) {
  const totalPages = Math.ceil(allVideos.length / ITEMS_PER_PAGE);
  if (page < 1 || page > totalPages) return;
  
  currentPage = page;
  renderPage();
  
  // Scroll to top of table
  document.querySelector('.table-container')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openScriptModal(filename) {
  currentScriptFilename = filename;
  const modal = document.getElementById('scriptModal');
  const area = document.getElementById('scriptArea');
  const title = document.getElementById('scriptModalTitle');

  title.textContent = `Manual Script: ${filename}`;
  area.value = manualScripts.get(filename) || '';
  modal.classList.remove('hidden');
}

function closeScriptModal() {
  document.getElementById('scriptModal').classList.add('hidden');
  currentScriptFilename = null;
}

function saveScript() {
  if (!currentScriptFilename) return;
  const area = document.getElementById('scriptArea');
  const text = area.value.trim();

  if (text) {
    manualScripts.set(currentScriptFilename, text);
  } else {
    manualScripts.delete(currentScriptFilename);
  }

  // Refresh only the button in the table
  const row = document.querySelector(
    `tr[data-filename="${currentScriptFilename}"]`
  );
  if (row) {
    const btn = row.querySelector('button[onclick*="openScriptModal"]');
    if (text) {
      btn.className = 'btn btn-success btn-small';
      btn.textContent = '📝 Edit';
    } else {
      btn.className = 'btn secondary btn-small';
      btn.textContent = '➕ Add';
    }
  }
  closeScriptModal();
}

function previewVideo(type, filename) {
  const modal = document.getElementById('videoModal');
  const player = document.getElementById('previewPlayer');
  const title = document.getElementById('modalTitle');

  modal.classList.remove('hidden');

  // Clear player first to avoid cache issues
  player.src = '';

  // Build URL with cache buster to avoid browser caching issues
  const timestamp = Date.now();
  player.src = `/videos/${type}/${encodeURIComponent(filename)}?t=${timestamp}`;
  title.textContent =
    type === 'input' ? `Input: ${filename}` : `Result: ${filename}`;

  // Add error handler for video loading
  player.onerror = function () {
    console.error(`Failed to load video: ${player.src}`);
    // Removed alert to avoid false positives
  };

  player.onloadeddata = function () {
    player.play();
  };
}

function previewResult(inputFilename) {
  const row = document.querySelector(`tr[data-filename="${inputFilename}"]`);
  const link = row.querySelector('.download-link');
  if (link && link.href && !link.classList.contains('hidden')) {
    const url = new URL(link.href);
    const outputFilename = url.pathname.split('/').pop();

    const modal = document.getElementById('videoModal');
    const player = document.getElementById('previewPlayer');
    const title = document.getElementById('modalTitle');

    modal.classList.remove('hidden');

    // Clear and set with cache buster
    player.src = '';
    player.src = `/videos/output/${encodeURIComponent(
      outputFilename
    )}?t=${Date.now()}`;
    title.textContent = `Result: ${outputFilename}`;

    player.onerror = function () {
      console.error(`Failed to load result video: ${player.src}`);
      // Removed alert to avoid false positives
    };

    player.onloadeddata = function () {
      player.play();
    };
  }
}

function closeModal() {
  const modal = document.getElementById('videoModal');
  const player = document.getElementById('previewPlayer');
  modal.classList.add('hidden');
  player.pause();
  player.src = '';
}

// Reset a row to Idle state and clear cached SRT
async function resetRow(filename) {
  const row = document.querySelector(`tr[data-filename="${filename}"]`);
  if (!row) return;

  const statusBadge = row.querySelector('.badge');
  const processBtn = row.querySelector('.process-btn');
  const durationEl = row.querySelector('.metric-duration');
  const progressEl = row.querySelector('.metric-progress');

  // Reset UI
  statusBadge.className = 'badge idle';
  statusBadge.textContent = 'Idle';
  processBtn.disabled = false;
  processBtn.textContent = 'Process';
  durationEl.textContent = '-';
  progressEl.textContent = '0%';

  // Remove task association and cached script
  processedTasks.delete(filename);
  manualScripts.delete(filename);

  // Update Script button back to Add
  const scriptBtn = row.querySelector('button[onclick*="openScriptModal"]');
  if (scriptBtn) {
    scriptBtn.className = 'btn secondary btn-small';
    scriptBtn.textContent = '➕ Add';
  }

  // Call API to delete cached SRT files
  try {
    await fetch('/api/clear-cache', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: filename }),
    });
    console.log(`Reset + cleared cache: ${filename}`);
  } catch (err) {
    console.error('Failed to clear cache', err);
  }
}

async function startProcess(filename) {
  const row = document.querySelector(`tr[data-filename="${filename}"]`);
  if (!row) return;

  const renameInput = row.querySelector('.rename-input');
  const dubCheck = row.querySelector('.dub-check');
  const statusBadge = row.querySelector('.badge');
  const processBtn = row.querySelector('.process-btn');

  // Get Settings
  const targetLang = document.getElementById('targetLang').value;
  const modelSize = document.getElementById('modelSize').value;
  const translationEngine = document.getElementById('translationEngine').value;
  const ollamaModel = document.getElementById('ollamaModel').value;

  // Dubbing Settings
  const dubVoice = document.getElementById('dubVoice').value;
  const audioMerge = document.getElementById('audioMerge').checked;

  // Per-video Dubbing
  const dubbingEnabled = dubCheck.checked;
  const renameTo = renameInput.value;

  // Manual Logic
  const scriptText = manualScripts.get(filename);
  let manual_srt = null;
  let manual_script = null;

  if (scriptText) {
    if (scriptText.includes('-->')) {
      manual_srt = scriptText;
    } else {
      manual_script = scriptText;
    }
  }

  statusBadge.className = 'badge queued';
  statusBadge.textContent = 'Queuing...';
  processBtn.disabled = true;

  try {
    const res = await fetch('/api/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: filename,
        rename_to: renameTo,
        dubbing: dubbingEnabled,
        manual_srt: manual_srt,
        manual_script: manual_script,
        settings: {
          targetLang: targetLang,
          model: modelSize,
          translationEngine: translationEngine,
          ollamaModel: ollamaModel,
          voice: dubVoice,
          audioMerge: audioMerge,
          geminiApiKey:
            document.getElementById('geminiApiKey')?.value ||
            localStorage.getItem('geminiApiKey') ||
            '',
          subtitleColor: document.getElementById('subtitleColor').value,
          subtitlePosition: document.getElementById('subtitlePosition').value,
          subtitleBgOpacity: document.getElementById('subtitleBgOpacity').value,
        },
      }),
    });
    const data = await res.json();
    const taskId = data.task_id;

    processedTasks.set(filename, taskId);
    pollStatus(taskId, row);
  } catch (err) {
    statusBadge.className = 'badge error';
    statusBadge.textContent = 'Req Failed';
    processBtn.disabled = false;
    console.error(err);
  }
}

// Queue for sequential processing
let isProcessingAll = false;
let processAllQueue = [];

async function processAll() {
  if (isProcessingAll) {
    alert('Already processing all videos. Please wait.');
    return;
  }

  const rows = document.querySelectorAll('#videoTableBody tr');
  processAllQueue = [];

  // Collect all videos that can be processed
  rows.forEach((row) => {
    const filename = row.dataset.filename;
    const btn = row.querySelector('.process-btn');
    if (!btn.disabled) {
      processAllQueue.push(filename);
    }
  });

  if (processAllQueue.length === 0) {
    alert('No videos to process.');
    return;
  }

  isProcessingAll = true;
  const btn = document.getElementById('processAllBtn');
  btn.textContent = `Processing 0/${processAllQueue.length}...`;
  btn.disabled = true;

  // Process sequentially
  for (let i = 0; i < processAllQueue.length; i++) {
    const filename = processAllQueue[i];
    btn.textContent = `Processing ${i + 1}/${processAllQueue.length}...`;

    try {
      await processAndWait(filename);
    } catch (err) {
      console.error(`Failed to process ${filename}:`, err);
      // Continue with next video even if one fails
    }
  }

  // Done
  isProcessingAll = false;
  btn.textContent = 'Process All';
  btn.disabled = false;
  alert('All videos processed!');
}

// Process a single video and wait for it to complete
function processAndWait(filename) {
  return new Promise(async (resolve, reject) => {
    const row = document.querySelector(`tr[data-filename="${filename}"]`);
    if (!row) {
      reject(new Error('Row not found'));
      return;
    }

    // Start processing
    await startProcess(filename);

    // Wait for task to complete by polling
    const taskId = processedTasks.get(filename);
    if (!taskId) {
      reject(new Error('No task ID'));
      return;
    }

    // Poll until done or error
    const checkInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${taskId}`);
        const data = await res.json();

        if (data.status === 'done' || data.status === 'error') {
          clearInterval(checkInterval);
          resolve(data);
        }
      } catch (err) {
        clearInterval(checkInterval);
        reject(err);
      }
    }, 2000);
  });
}

function pollStatus(taskId, rowElement) {
  const statusBadge = rowElement.querySelector('.badge');
  const processBtn = rowElement.querySelector('.process-btn');
  const durationEl = rowElement.querySelector('.metric-duration');
  const progressEl = rowElement.querySelector('.metric-progress');
  const downloadLink = rowElement.querySelector('.download-link');
  const watchBtn = rowElement.querySelector('.watch');
  const previewBtn = rowElement.querySelector('.preview-btn');

  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${taskId}`);
      const data = await res.json();

      let badgeClass = 'idle';
      if (data.status === 'processing') badgeClass = 'processing';
      else if (data.status === 'done') badgeClass = 'done';
      else if (data.status === 'error') badgeClass = 'error';
      else if (data.status === 'queued') badgeClass = 'queued';

      statusBadge.className = `badge ${badgeClass}`;
      statusBadge.textContent = data.message || data.status;

      if (data.duration) {
        durationEl.textContent = data.duration;
      }

      if (data.status === 'processing' && data.start_time) {
        // Live Timer
        const elapsed = Math.floor(Date.now() / 1000 - data.start_time);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        durationEl.textContent = `${mins}m ${secs}s`;
      }

      if (data.progress !== undefined)
        progressEl.textContent = data.progress + '%';

      if (data.status === 'done' || data.status === 'error') {
        clearInterval(interval);
        processBtn.disabled = false;
        processBtn.textContent = 'Retry';

        if (data.status === 'done' && data.output_file) {
          downloadLink.href = `/videos/output/${data.output_file}`;
          downloadLink.classList.remove('hidden');

          // Show Watch Button
          watchBtn.classList.remove('hidden');

          // Upgrade Main Preview Button to Show Output
          previewBtn.onclick = () => previewVideo('output', data.output_file);
          previewBtn.title = 'Watch Result: ' + data.output_file;
          previewBtn.innerHTML = '✅'; // Visual Indicator
          previewBtn.style.color = 'var(--success)';

          // Auto-load SRT content into Script modal
          if (data.srt_content) {
            const filename = rowElement.dataset.filename;
            manualScripts.set(filename, data.srt_content);

            // Update Script button to show "Edit"
            const scriptBtn = rowElement.querySelector(
              'button[onclick*="openScriptModal"]'
            );
            if (scriptBtn) {
              scriptBtn.className = 'btn btn-success btn-small';
              scriptBtn.textContent = '📝 Edit';
            }
          }
        }
      }
    } catch (err) {
      console.error('Poll error', err);
    }
  }, 2000);
}

// Download all completed videos sequentially
async function downloadAll() {
  const rows = document.querySelectorAll('#videoTableBody tr');
  const downloadQueue = [];

  // Collect all download links that are visible (completed videos)
  rows.forEach((row) => {
    const downloadLink = row.querySelector('.download-link');
    if (
      downloadLink &&
      !downloadLink.classList.contains('hidden') &&
      downloadLink.href
    ) {
      downloadQueue.push({
        filename: row.dataset.filename,
        url: downloadLink.href,
      });
    }
  });

  if (downloadQueue.length === 0) {
    alert('No completed videos to download.');
    return;
  }

  const btn = document.getElementById('downloadAllBtn');
  btn.disabled = true;

  // Download sequentially with delay
  for (let i = 0; i < downloadQueue.length; i++) {
    const item = downloadQueue[i];
    btn.textContent = `Downloading ${i + 1}/${downloadQueue.length}...`;

    // Create temporary download link and click it
    const a = document.createElement('a');
    a.href = item.url;
    a.download = item.url.split('/').pop();
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    // Wait 1 second before next download (prevent browser blocking)
    if (i < downloadQueue.length - 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  btn.textContent = 'Download All';
  btn.disabled = false;
  alert(`Downloaded ${downloadQueue.length} videos!`);
}
async function handleFileUpload(input) {
  if (input.files && input.files[0]) {
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    // UI Feedback (optional, could add a spinner or toast)
    const btn = document.querySelector('button[onclick*="videoUploadInput"]');
    const originalText = btn.textContent;
    btn.textContent = '⏳ Uploading...';
    btn.disabled = true;

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      
      if (data.success) {
        alert('Upload successful: ' + data.message);
        fetchVideos(); // Refresh list
      } else {
        alert('Upload failed: ' + data.error);
      }
    } catch (err) {
      console.error('Upload error:', err);
      alert('Upload failed due to network error.');
    } finally {
      btn.textContent = originalText;
      btn.disabled = false;
      input.value = ''; // Reset input
    }
  }
}
