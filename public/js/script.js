// ═══════════════════════════════════════════════════════════════════════════
// KACHAKA CARE // COMMAND CENTER — Main Application Script
// Single robot (robot_id = "kachaka"), 5-tab SPA
// ═══════════════════════════════════════════════════════════════════════════

// --- Global State ---
let tasks = [];
let currentTab = 'dashboard';
let pollingInterval = null;
let robotData = { battery: null, pose: null, status: 'unknown' };

// Map description (VAC map)
const gMapDesc = {
  w: 1060, h: 827,
  origin: { x: -29.4378, y: -26.3988 },
  resolution: 0.05,
};

// ═══════════════════════════════════════════════════════════════════════════
// COORDINATE TRANSFORM
// ═══════════════════════════════════════════════════════════════════════════

function tfROS2Canvas(mapDesc, rosPt) {
  if (!mapDesc || !mapDesc.origin || !mapDesc.resolution || !mapDesc.h) return {};
  const xRosOffset = mapDesc.origin.x / mapDesc.resolution;
  const yRosOffset = mapDesc.origin.y / mapDesc.resolution;
  const xCanvas = (rosPt.x / mapDesc.resolution - xRosOffset).toFixed(4);
  let yCanvas = (rosPt.y / mapDesc.resolution - yRosOffset);
  yCanvas = (mapDesc.h - yCanvas).toFixed(4);
  return { x: parseFloat(xCanvas), y: parseFloat(yCanvas) };
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════

function switchTab(tabName) {
  currentTab = tabName;

  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });

  // Update tab content
  document.querySelectorAll('.tab-content').forEach(view => {
    view.classList.toggle('active', view.id === `view-${tabName}`);
  });

  // Load tab-specific data on switch
  switch (tabName) {
    case 'dashboard': loadDashboardData(); break;
    case 'patrol': loadPatrolConfig(); break;
    case 'beds': loadBedsConfig(); break;
    case 'sensor': loadSensorData(); break;
    case 'settings': loadSettings(); break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// COLLAPSIBLE MONITOR FRAMES
// ═══════════════════════════════════════════════════════════════════════════

function toggleFrame(frameId) {
  const frame = document.getElementById(frameId);
  if (!frame) return;
  frame.classList.toggle('collapsed');
  const icon = frame.querySelector('.toggle-icon');
  if (icon) icon.textContent = frame.classList.contains('collapsed') ? '▶' : '▼';
}

// ═══════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════════════════

window.addEventListener('DOMContentLoaded', async () => {
  // Bind tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Bind button events
  const btnHome = document.getElementById('btn-home');
  if (btnHome) btnHome.addEventListener('click', returnHome);

  const btnCancel = document.getElementById('btn-cancel-command');
  if (btnCancel) btnCancel.addEventListener('click', returnHome);

  // Initialize map
  initMap();

  // Load initial data
  await loadDashboardData();

  // Start polling
  startPolling();

  // Start map animation
  animateMap();
});

// ═══════════════════════════════════════════════════════════════════════════
// DATA POLLING
// ═══════════════════════════════════════════════════════════════════════════

function startPolling() {
  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(async () => {
    try {
      await Promise.all([
        fetchRobotStatus(),
        fetchTaskStatus(),
      ]);
      // Check for shelf-drop
      checkShelfDrop();
    } catch (e) {
      console.error('Polling error:', e);
    }
  }, 2000);
}

async function fetchRobotStatus() {
  try {
    const [batteryRes, poseRes] = await Promise.all([
      dataService.getRobotBattery(),
      dataService.getRobotPose(),
    ]);

    // Battery
    const battery = batteryRes?.remaining_percentage;
    if (battery !== undefined) {
      robotData.battery = battery;
      const el = document.getElementById('battery-value');
      if (el) el.textContent = `${Math.round(battery)}%`;
    }

    // Pose
    const pose = poseRes;
    if (pose && pose.x !== undefined) {
      robotData.pose = pose;
      const poseEl = document.getElementById('pose-display');
      if (poseEl) {
        poseEl.textContent = `X: ${pose.x.toFixed(2)} Y: ${pose.y.toFixed(2)} θ: ${(pose.theta || 0).toFixed(2)}`;
      }
    }

    // Update status
    robotData.status = 'online';
    const statusEl = document.getElementById('robot-status-value');
    if (statusEl) statusEl.textContent = 'Online';
    const connEl = document.getElementById('connection-status');
    if (connEl) {
      connEl.classList.remove('disconnected');
      connEl.classList.add('connected');
    }
  } catch (e) {
    robotData.status = 'offline';
    const statusEl = document.getElementById('robot-status-value');
    if (statusEl) statusEl.textContent = 'Offline';
    const connEl = document.getElementById('connection-status');
    if (connEl) {
      connEl.classList.remove('connected');
      connEl.classList.add('disconnected');
    }
  }
}

async function fetchTaskStatus() {
  try {
    const response = await dataService.getTasks();
    const tasksData = Array.isArray(response) ? response : (response?.data || []);
    tasks = tasksData;

    // Update patrol history in dashboard if visible
    if (currentTab === 'dashboard') {
      renderPatrolHistory();
    }
  } catch (e) {
    console.error('Failed to fetch tasks:', e);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SHELF DROP DETECTION & RECOVERY
// ═══════════════════════════════════════════════════════════════════════════

function checkShelfDrop() {
  const shelfDropTask = tasks.find(t => t.status === 'shelf_dropped');
  const overlay = document.getElementById('shelf-drop-overlay');
  if (!overlay) return;

  if (shelfDropTask) {
    const meta = shelfDropTask.metadata || {};
    const roomEl = document.getElementById('shelf-drop-room');
    if (roomEl) roomEl.textContent = meta.room || meta.bed_key || 'unknown';
    overlay.style.display = 'flex';
  } else {
    overlay.style.display = 'none';
  }
}

async function recoverShelf() {
  const statusEl = document.getElementById('shelf-recovery-status');
  if (statusEl) statusEl.textContent = 'Recovering...';

  try {
    // Get shelf_id from patrol config
    const patrol = await dataService.getPatrol();
    const shelfId = patrol?.shelf_id || 'S_04';

    // Get the shelf-dropped task for location info
    const shelfDropTask = tasks.find(t => t.status === 'shelf_dropped');
    const locationId = shelfDropTask?.metadata?.location_id || '';

    const result = await dataService.recoverShelf(shelfId, locationId);
    if (statusEl) statusEl.textContent = 'Recovery successful!';
    setTimeout(() => {
      document.getElementById('shelf-drop-overlay').style.display = 'none';
      if (statusEl) statusEl.textContent = '';
    }, 2000);
  } catch (e) {
    if (statusEl) statusEl.textContent = `Recovery failed: ${e.message || e}`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════

async function loadDashboardData() {
  loadLatestBioSensor();
  renderPatrolHistory();
}

async function loadLatestBioSensor() {
  try {
    const res = await dataService.getLatestBioSensor();
    if (res.status === 'success' && res.data) {
      const d = res.data;
      const bpmEl = document.getElementById('bio-bpm');
      const rpmEl = document.getElementById('bio-rpm');
      const statusEl = document.getElementById('bio-status');
      if (bpmEl) bpmEl.textContent = d.bpm || '--';
      if (rpmEl) rpmEl.textContent = d.rpm || '--';
      if (statusEl) statusEl.textContent = d.status || '--';
    }
  } catch (e) {
    console.error('Failed to load bio sensor:', e);
  }
}

function renderPatrolHistory() {
  const container = document.getElementById('patrol-history-list');
  if (!container) return;

  const recentTasks = tasks.slice(0, 10);
  if (recentTasks.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:12px;">No patrol history yet</p>';
    return;
  }

  container.innerHTML = recentTasks.map(t => {
    const statusColor = t.status === 'done' ? 'var(--mint)' :
                        t.status === 'failed' ? 'var(--coral)' :
                        t.status === 'shelf_dropped' ? 'var(--warning)' :
                        t.status === 'running' ? 'var(--amber)' : 'var(--text-muted)';
    const time = t.created_at ? new Date(t.created_at).toLocaleString() : '--';
    return `<div style="padding:6px 0;border-bottom:1px solid var(--border-subtle);display:flex;justify-content:space-between;font-size:12px;">
      <span>${t.task_id}</span>
      <span style="color:${statusColor};font-weight:600;">${t.status}</span>
    </div>`;
  }).join('');
}

// Quick actions
async function resetShelfSensor() {
  try {
    await dataService.resetShelfPose('S04', '');
    alert('生理感測器歸位成功');
  } catch (e) {
    alert('歸位失敗: ' + (e.message || e));
  }
}

async function returnHome() {
  try {
    await dataService.returnHome();
  } catch (e) {
    console.error('Return home failed:', e);
  }
}

async function startDemoRun() {
  try {
    const res = await dataService.startPatrol('demo');
    alert('Demo Run started! Task: ' + (res.task_id || 'created'));
  } catch (e) {
    alert('Failed to start demo run: ' + (e.message || e));
  }
}

async function startPatrol() {
  try {
    const res = await dataService.startPatrol('patrol');
    alert('Patrol started! Task: ' + (res.task_id || 'created'));
  } catch (e) {
    alert('Failed to start patrol: ' + (e.message || e));
  }
}

// Manual control (D-pad)
async function manualControl(direction) {
  if (!robotData.pose) return;
  const step = 0.1;
  const angleStep = 0.174533; // ~10 degrees
  let { x, y, theta } = robotData.pose;
  theta = theta || 0;

  switch (direction) {
    case 'forward':
      x += step * Math.cos(theta);
      y += step * Math.sin(theta);
      break;
    case 'backward':
      x -= step * Math.cos(theta);
      y -= step * Math.sin(theta);
      break;
    case 'left': theta += angleStep; break;
    case 'right': theta -= angleStep; break;
  }

  try {
    await dataService.moveToPose(x, y, theta);
  } catch (e) {
    console.error('Manual control failed:', e);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MAP RENDERING
// ═══════════════════════════════════════════════════════════════════════════

let mapState = {
  canvas: null, ctx: null, img: null,
  view: { tx: 0, ty: 0, scale: 1, minScale: 0.3, maxScale: 5, dragging: false, lastX: 0, lastY: 0 },
  robotPos: null, robotTheta: 0, targetTheta: 0,
};

function initMap() {
  const container = document.getElementById('map-container');
  const canvas = document.getElementById('map-canvas');
  if (!canvas || !container) return;

  const w = container.clientWidth || 800;
  const h = container.clientHeight || 600;
  canvas.width = w;
  canvas.height = h;
  mapState.canvas = canvas;
  mapState.ctx = canvas.getContext('2d');
  mapState.view.tx = w / 2 - gMapDesc.w / 2;
  mapState.view.ty = h / 2 - gMapDesc.h / 2;

  // Load map image
  const img = new Image();
  img.src = 'vac_map.png';
  img.onload = () => {
    mapState.img = img;
    const loading = document.getElementById('map-loading');
    if (loading) loading.style.display = 'none';
    drawMap();
  };

  // Pan & zoom events
  canvas.style.cursor = 'grab';

  canvas.addEventListener('mousedown', e => {
    mapState.view.dragging = true;
    mapState.view.lastX = e.clientX;
    mapState.view.lastY = e.clientY;
    canvas.style.cursor = 'grabbing';
  });
  window.addEventListener('mousemove', e => {
    if (!mapState.view.dragging) return;
    mapState.view.tx += e.clientX - mapState.view.lastX;
    mapState.view.ty += e.clientY - mapState.view.lastY;
    mapState.view.lastX = e.clientX;
    mapState.view.lastY = e.clientY;
    drawMap();
  });
  window.addEventListener('mouseup', () => {
    mapState.view.dragging = false;
    canvas.style.cursor = 'grab';
  });

  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const mx = e.offsetX, my = e.offsetY;
    const mapX = (mx - mapState.view.tx) / mapState.view.scale;
    const mapY = (my - mapState.view.ty) / mapState.view.scale;
    let s = mapState.view.scale * (e.deltaY < 0 ? 1.1 : 0.9);
    s = Math.max(mapState.view.minScale, Math.min(mapState.view.maxScale, s));
    mapState.view.tx = mx - mapX * s;
    mapState.view.ty = my - mapY * s;
    mapState.view.scale = s;
    drawMap();
  }, { passive: false });

  canvas.addEventListener('dblclick', () => {
    mapState.view.tx = w / 2 - gMapDesc.w / 2;
    mapState.view.ty = h / 2 - gMapDesc.h / 2;
    mapState.view.scale = 1;
    drawMap();
  });

  // Touch events
  let touchState = { lastDist: 0, lastCenter: { x: 0, y: 0 } };

  canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    if (e.touches.length === 1) {
      mapState.view.dragging = true;
      mapState.view.lastX = e.touches[0].clientX;
      mapState.view.lastY = e.touches[0].clientY;
    } else if (e.touches.length === 2) {
      mapState.view.dragging = false;
      const dx = e.touches[1].clientX - e.touches[0].clientX;
      const dy = e.touches[1].clientY - e.touches[0].clientY;
      touchState.lastDist = Math.sqrt(dx * dx + dy * dy);
      touchState.lastCenter = {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2
      };
    }
  }, { passive: false });

  canvas.addEventListener('touchmove', e => {
    e.preventDefault();
    if (e.touches.length === 1 && mapState.view.dragging) {
      const t = e.touches[0];
      mapState.view.tx += t.clientX - mapState.view.lastX;
      mapState.view.ty += t.clientY - mapState.view.lastY;
      mapState.view.lastX = t.clientX;
      mapState.view.lastY = t.clientY;
      drawMap();
    } else if (e.touches.length === 2) {
      const dx = e.touches[1].clientX - e.touches[0].clientX;
      const dy = e.touches[1].clientY - e.touches[0].clientY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const center = {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2
      };
      const rect = canvas.getBoundingClientRect();
      const cx = center.x - rect.left;
      const cy = center.y - rect.top;
      const mapX = (cx - mapState.view.tx) / mapState.view.scale;
      const mapY = (cy - mapState.view.ty) / mapState.view.scale;
      let s = mapState.view.scale * (dist / touchState.lastDist);
      s = Math.max(mapState.view.minScale, Math.min(mapState.view.maxScale, s));
      mapState.view.tx = cx - mapX * s;
      mapState.view.ty = cy - mapY * s;
      mapState.view.scale = s;
      touchState.lastDist = dist;
      touchState.lastCenter = center;
      drawMap();
    }
  }, { passive: false });

  canvas.addEventListener('touchend', e => {
    e.preventDefault();
    if (e.touches.length === 0) {
      mapState.view.dragging = false;
    } else if (e.touches.length === 1) {
      mapState.view.dragging = true;
      mapState.view.lastX = e.touches[0].clientX;
      mapState.view.lastY = e.touches[0].clientY;
    }
  }, { passive: false });

  // Resize observer
  new ResizeObserver(() => {
    const nw = container.clientWidth;
    const nh = container.clientHeight;
    if (nw > 0 && nh > 0) {
      canvas.width = nw;
      canvas.height = nh;
      drawMap();
    }
  }).observe(container);
}

function drawMap() {
  const { canvas, ctx, img, view } = mapState;
  if (!ctx || !canvas) return;

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.translate(view.tx, view.ty);
  ctx.scale(view.scale, view.scale);

  // Draw map image
  if (img) {
    ctx.drawImage(img, 0, 0, gMapDesc.w, gMapDesc.h);
  }

  // Draw labeled areas
  drawArea(ctx, { x: 595, y: 170, w: 60, h: 25, theta: 0, fillColor: '#0099ff', name: '物流區' });
  drawArea(ctx, { x: 555, y: 110, w: 50, h: 20, theta: -Math.PI / 2, fillColor: '#ff0000', name: '櫃台' });
  drawArea(ctx, { x: 580, y: 480, w: 60, h: 20, theta: Math.PI / 6, fillColor: '#00ff00', name: '護理站' });

  // Draw robot
  if (robotData.pose) {
    const pos = tfROS2Canvas(gMapDesc, robotData.pose);
    if (pos.x && pos.y) {
      ctx.save();
      ctx.translate(pos.x, pos.y);
      ctx.rotate(mapState.robotTheta || 0);

      // Robot sprite
      const sprite = mapState._robotSprite;
      if (sprite && sprite.complete) {
        ctx.drawImage(sprite, -8, -5, 16, 10);
      } else {
        // Fallback triangle
        ctx.fillStyle = '#ff8800';
        ctx.beginPath();
        ctx.moveTo(0, -10);
        ctx.lineTo(-7, 7);
        ctx.lineTo(7, 7);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();

      // Origin point
      const origin = tfROS2Canvas(gMapDesc, { x: 0, y: 0 });
      ctx.beginPath();
      ctx.arc(origin.x, origin.y, 4, 0, 2 * Math.PI);
      ctx.fillStyle = 'red';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }

  ctx.restore();
}

function drawArea(ctx, area) {
  ctx.save();
  ctx.globalAlpha = 0.5;
  ctx.translate(area.x, area.y);
  ctx.rotate(area.theta || 0);
  ctx.fillStyle = area.fillColor;
  ctx.fillRect(-area.w / 2, -area.h / 2, area.w, area.h);
  ctx.restore();

  ctx.save();
  ctx.translate(area.x, area.y);
  ctx.rotate(area.theta || 0);
  ctx.font = '18px Arial';
  ctx.fillStyle = '#000';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(area.name, 0, 0);
  ctx.restore();
}

function animateMap() {
  // Smooth robot orientation interpolation
  if (robotData.pose && robotData.pose.theta !== undefined) {
    const target = -robotData.pose.theta; // Convert CCW to CW for canvas
    const current = mapState.robotTheta || 0;
    const diff = normalizeAngle(target - current);
    if (Math.abs(diff) > 0.017) {
      mapState.robotTheta = normalizeAngle(current + diff * 0.1);
    } else {
      mapState.robotTheta = target;
    }
  }

  drawMap();
  requestAnimationFrame(animateMap);
}

function normalizeAngle(a) {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
}

// Load robot sprite
(function () {
  const sprite = new Image();
  sprite.src = 'assets/icons/kachaka.png';
  mapState._robotSprite = sprite;
})();

// ═══════════════════════════════════════════════════════════════════════════
// PATROL TAB
// ═══════════════════════════════════════════════════════════════════════════

let patrolConfig = null;
let bedsConfig = null;
let scheduleConfig = null;

async function loadPatrolConfig() {
  try {
    const [patrol, beds, schedule] = await Promise.all([
      dataService.getPatrol(),
      dataService.getBeds(),
      dataService.getSchedules(),
    ]);
    patrolConfig = patrol;
    bedsConfig = beds;
    scheduleConfig = schedule;

    // Shelf ID
    const shelfInput = document.getElementById('patrol-shelf-id');
    if (shelfInput) shelfInput.value = patrol.shelf_id || '';

    // Render schedule list
    renderScheduleList();

    // Render patrol route
    renderPatrolRoute();
  } catch (e) {
    console.error('Failed to load patrol config:', e);
  }
}

function renderScheduleList() {
  const container = document.getElementById('schedule-list');
  if (!container || !scheduleConfig) return;

  const schedules = scheduleConfig.schedules || [];
  if (schedules.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:12px;">No schedules configured</p>';
    return;
  }

  container.innerHTML = schedules.map(s => `
    <div class="schedule-item">
      <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="toggleSchedule('${s.id}', this.checked)">
      <span class="schedule-time">${s.time}</span>
      <span class="schedule-type">${s.type === 'weekday' ? 'Weekdays' : 'Daily'}</span>
      <button class="remove-btn" onclick="removeSchedule('${s.id}')" title="Remove">✕</button>
    </div>
  `).join('');
}

async function addSchedule() {
  const timeInput = document.getElementById('new-schedule-time');
  const typeSelect = document.getElementById('new-schedule-type');
  if (!timeInput || !timeInput.value) return;

  const newSchedule = {
    id: 'sched-' + Date.now(),
    enabled: true,
    time: timeInput.value,
    type: typeSelect ? typeSelect.value : 'daily',
  };

  if (!scheduleConfig) scheduleConfig = { schedules: [] };
  scheduleConfig.schedules.push(newSchedule);

  try {
    await dataService.saveSchedules(scheduleConfig);
    renderScheduleList();
    timeInput.value = '';
  } catch (e) {
    alert('Failed to save schedule: ' + e.message);
  }
}

async function removeSchedule(scheduleId) {
  try {
    await dataService.deleteSchedule(scheduleId);
    if (scheduleConfig) {
      scheduleConfig.schedules = scheduleConfig.schedules.filter(s => s.id !== scheduleId);
    }
    renderScheduleList();
  } catch (e) {
    alert('Failed to remove schedule: ' + e.message);
  }
}

async function toggleSchedule(scheduleId, enabled) {
  if (!scheduleConfig) return;
  const s = scheduleConfig.schedules.find(s => s.id === scheduleId);
  if (s) s.enabled = enabled;
  try {
    await dataService.saveSchedules(scheduleConfig);
  } catch (e) {
    console.error('Failed to toggle schedule:', e);
  }
}

function renderPatrolRoute() {
  const container = document.getElementById('patrol-route-list');
  if (!container || !patrolConfig || !bedsConfig) return;

  const bedsOrder = patrolConfig.beds_order || [];
  const bedsMap = bedsConfig.beds || {};

  // Group beds by room
  const roomGroups = {};
  bedsOrder.forEach((entry, idx) => {
    const bedInfo = bedsMap[entry.bed_key] || {};
    const room = bedInfo.room || entry.bed_key.split('-')[0];
    if (!roomGroups[room]) roomGroups[room] = [];
    roomGroups[room].push({ ...entry, idx, location_id: bedInfo.location_id || '' });
  });

  let html = '';
  Object.keys(roomGroups).sort().forEach(room => {
    const beds = roomGroups[room];
    html += `<div class="patrol-room">
      <div class="patrol-room-header" onclick="this.parentElement.classList.toggle('collapsed')">
        <span class="room-label">Room ${room}</span>
        <span class="toggle-icon">▼</span>
      </div>
      <div class="patrol-bed-list">`;

    beds.forEach(bed => {
      html += `<div class="patrol-bed-item">
        <input type="checkbox" ${bed.enabled ? 'checked' : ''}
               onchange="togglePatrolBed(${bed.idx}, this.checked)">
        <span class="bed-label">${bed.bed_key} (${bed.location_id})</span>
        <div class="reorder-btns">
          <button onclick="movePatrolBed(${bed.idx}, -1)" title="Move up">▲</button>
          <button onclick="movePatrolBed(${bed.idx}, 1)" title="Move down">▼</button>
        </div>
      </div>`;
    });

    html += `</div></div>`;
  });

  container.innerHTML = html || '<p style="color:var(--text-muted);font-size:12px;">No patrol route configured. Set up beds first.</p>';
}

function togglePatrolBed(idx, enabled) {
  if (!patrolConfig || !patrolConfig.beds_order[idx]) return;
  patrolConfig.beds_order[idx].enabled = enabled;
}

function movePatrolBed(idx, direction) {
  if (!patrolConfig) return;
  const arr = patrolConfig.beds_order;
  const newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= arr.length) return;
  [arr[idx], arr[newIdx]] = [arr[newIdx], arr[idx]];
  renderPatrolRoute();
}

async function savePatrolConfig() {
  if (!patrolConfig) return;

  const shelfInput = document.getElementById('patrol-shelf-id');
  if (shelfInput) patrolConfig.shelf_id = shelfInput.value;

  try {
    await dataService.savePatrol(patrolConfig);
    alert('Patrol configuration saved!');
  } catch (e) {
    alert('Failed to save patrol config: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// BEDS TAB
// ═══════════════════════════════════════════════════════════════════════════

async function loadBedsConfig() {
  try {
    bedsConfig = await dataService.getBeds();
    renderBedsUI();
  } catch (e) {
    console.error('Failed to load beds config:', e);
  }
}

function renderBedsUI() {
  if (!bedsConfig) return;

  // Populate form fields
  const countEl = document.getElementById('beds-room-count');
  const startEl = document.getElementById('beds-room-start');
  const numbersEl = document.getElementById('beds-bed-numbers');

  if (countEl) countEl.value = bedsConfig.room_count || 14;
  if (startEl) startEl.value = bedsConfig.room_start || 101;
  if (numbersEl) numbersEl.value = (bedsConfig.bed_numbers || [1, 2, 3, 5, 6]).join(',');

  renderBedsGrid();
}

function renderBedsGrid() {
  const container = document.getElementById('beds-grid-container');
  if (!container || !bedsConfig) return;

  const beds = bedsConfig.beds || {};
  const roomCount = bedsConfig.room_count || 14;
  const roomStart = bedsConfig.room_start || 101;
  const bedNumbers = bedsConfig.bed_numbers || [1, 2, 3, 5, 6];

  let html = '';
  for (let r = 0; r < roomCount; r++) {
    const room = roomStart + r;
    html += `<div class="room-section">
      <h4>Room ${room}</h4>
      <div class="beds-grid">`;

    bedNumbers.forEach(bedNum => {
      const key = `${room}-${bedNum}`;
      const bed = beds[key] || {};
      html += `<div class="bed-card">
        <div class="bed-key">${key}</div>
        <input type="text" id="bed-loc-${key}" value="${bed.location_id || ''}"
               placeholder="Location ID" onchange="updateBedLocationId('${key}', this.value)">
      </div>`;
    });

    html += `</div></div>`;
  }

  container.innerHTML = html;
}

function updateBedLocationId(bedKey, locationId) {
  if (!bedsConfig) return;
  if (!bedsConfig.beds) bedsConfig.beds = {};
  if (!bedsConfig.beds[bedKey]) {
    const parts = bedKey.split('-');
    bedsConfig.beds[bedKey] = { room: parseInt(parts[0]), bed: parseInt(parts[1]), location_id: locationId };
  } else {
    bedsConfig.beds[bedKey].location_id = locationId;
  }
}

function regenerateBeds() {
  const countEl = document.getElementById('beds-room-count');
  const startEl = document.getElementById('beds-room-start');
  const numbersEl = document.getElementById('beds-bed-numbers');

  const roomCount = parseInt(countEl?.value) || 14;
  const roomStart = parseInt(startEl?.value) || 101;
  const bedNumbers = (numbersEl?.value || '1,2,3,5,6').split(',').map(n => parseInt(n.trim())).filter(n => !isNaN(n));

  const beds = {};
  for (let r = 0; r < roomCount; r++) {
    const room = roomStart + r;
    bedNumbers.forEach(bedNum => {
      const key = `${room}-${bedNum}`;
      beds[key] = {
        room: room,
        bed: bedNum,
        location_id: `B_${key}`
      };
    });
  }

  bedsConfig = { room_count: roomCount, room_start: roomStart, bed_numbers: bedNumbers, beds };
  renderBedsGrid();
}

async function fetchRobotLocations() {
  try {
    const locations = await dataService.getRobotLocations();
    if (!Array.isArray(locations)) {
      alert('Unexpected response format');
      return;
    }

    // Auto-populate location IDs in bed cards
    locations.forEach(loc => {
      const name = loc.name || loc.id || '';
      // Try to match location name to bed key (e.g., "B_101-1" → "101-1")
      const match = name.match(/B_(\d+-\d+)/);
      if (match) {
        const bedKey = match[1];
        const input = document.getElementById(`bed-loc-${bedKey}`);
        if (input) {
          input.value = name;
          updateBedLocationId(bedKey, name);
        }
      }
    });

    alert(`Fetched ${locations.length} locations from robot`);
  } catch (e) {
    alert('Failed to fetch robot locations: ' + (e.message || e));
  }
}

async function saveBedsConfig() {
  if (!bedsConfig) return;
  try {
    await dataService.saveBeds(bedsConfig);
    alert('Beds configuration saved!');
  } catch (e) {
    alert('Failed to save beds config: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SENSOR TAB
// ═══════════════════════════════════════════════════════════════════════════

let sensorData = [];

async function loadSensorData() {
  try {
    const bedFilter = document.getElementById('sensor-filter-bed')?.value || '';
    const limit = parseInt(document.getElementById('sensor-filter-limit')?.value) || 100;

    const params = { limit };
    if (bedFilter) params.task_id = bedFilter;

    const res = await dataService.getSensorHistory(params);
    sensorData = res.data || [];

    updateSensorStats();
    renderSensorTable();
  } catch (e) {
    console.error('Failed to load sensor data:', e);
  }
}

function updateSensorStats() {
  const total = sensorData.length;
  const valid = sensorData.filter(d => d.is_valid).length;
  const rate = total > 0 ? ((valid / total) * 100).toFixed(1) : '0';
  const bpmValues = sensorData.filter(d => d.bpm).map(d => d.bpm);
  const avgBpm = bpmValues.length > 0 ? (bpmValues.reduce((a, b) => a + b, 0) / bpmValues.length).toFixed(0) : '--';

  const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  el('stat-total-scans', total);
  el('stat-valid-scans', valid);
  el('stat-success-rate', rate + '%');
  el('stat-avg-bpm', avgBpm);
}

function renderSensorTable() {
  const tbody = document.getElementById('sensor-table-body');
  if (!tbody) return;

  if (sensorData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);">No data</td></tr>';
    return;
  }

  tbody.innerHTML = sensorData.map(d => {
    const time = d.timestamp ? new Date(d.timestamp).toLocaleString() : '--';
    const validClass = d.is_valid ? 'status-valid' : 'status-invalid';
    return `<tr>
      <td>${time}</td>
      <td>${d.task_id || '--'}</td>
      <td>${d.bed_id || '--'}</td>
      <td>${d.retry_count ?? '--'}</td>
      <td>${d.status ?? '--'}</td>
      <td>${d.bpm ?? '--'}</td>
      <td>${d.rpm ?? '--'}</td>
      <td class="${validClass}">${d.is_valid ? 'Valid' : 'Invalid'}</td>
    </tr>`;
  }).join('');
}

function exportSensorCSV() {
  if (sensorData.length === 0) {
    alert('No data to export');
    return;
  }

  const headers = ['timestamp', 'task_id', 'bed_id', 'retry_count', 'status', 'bpm', 'rpm', 'is_valid'];
  const rows = sensorData.map(d =>
    headers.map(h => JSON.stringify(d[h] ?? '')).join(',')
  );
  const csv = [headers.join(','), ...rows].join('\n');

  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `sensor_data_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ═══════════════════════════════════════════════════════════════════════════
// SETTINGS TAB
// ═══════════════════════════════════════════════════════════════════════════

const SETTINGS_MAP = [
  { id: 'setting-robot-ip', key: 'robot_ip' },
  { id: 'setting-mqtt-broker', key: 'mqtt_broker' },
  { id: 'setting-mqtt-port', key: 'mqtt_port', type: 'number' },
  { id: 'setting-mqtt-topic', key: 'mqtt_topic' },
  { id: 'setting-mqtt-enabled', key: 'mqtt_enabled', type: 'checkbox' },
  { id: 'setting-bio-scan-wait-time', key: 'bio_scan_wait_time', type: 'number' },
  { id: 'setting-bio-scan-retry-count', key: 'bio_scan_retry_count', type: 'number' },
  { id: 'setting-bio-scan-initial-wait', key: 'bio_scan_initial_wait', type: 'number' },
  { id: 'setting-bio-scan-valid-status', key: 'bio_scan_valid_status', type: 'number' },
  { id: 'setting-robot-max-retries', key: 'robot_max_retries', type: 'number' },
  { id: 'setting-robot-retry-base-delay', key: 'robot_retry_base_delay', type: 'number' },
  { id: 'setting-robot-retry-max-delay', key: 'robot_retry_max_delay', type: 'number' },
  { id: 'setting-enable-telegram', key: 'enable_telegram', type: 'checkbox' },
  { id: 'setting-telegram-bot-token', key: 'telegram_bot_token' },
  { id: 'setting-telegram-user-id', key: 'telegram_user_id' },
  { id: 'setting-gemini-api-key', key: 'gemini_api_key' },
];

async function loadSettings() {
  try {
    const settings = await dataService.getSettings();
    SETTINGS_MAP.forEach(({ id, key, type }) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (type === 'checkbox') {
        el.checked = !!settings[key];
      } else {
        el.value = settings[key] ?? '';
      }
    });
  } catch (e) {
    console.error('Failed to load settings:', e);
  }
}

async function saveSettings() {
  const data = {};
  SETTINGS_MAP.forEach(({ id, key, type }) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (type === 'checkbox') {
      data[key] = el.checked;
    } else if (type === 'number') {
      data[key] = parseFloat(el.value) || 0;
    } else {
      data[key] = el.value;
    }
  });

  try {
    await dataService.saveSettings(data);
    alert('Settings saved!');
  } catch (e) {
    alert('Failed to save settings: ' + e.message);
  }
}
