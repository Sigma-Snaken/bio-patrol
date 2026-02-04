// Kachaka Task Editing HMI Script

// Global tasks and robots array, should be fetched from API
let tasks = [];
let robots = [];

// Initialization
// Fake data: robot status and coordinates
let robotStatusList = [
  { robot_id: 'normal', name: 'Sigma 01', model: 'Kachaka S1', status: 'online', battery: 86, x: 60, y: 120, theta: 0, task: '巡邏', color: '#4e73df', avatar: 'assets/icons/kachaka.png', traj: null },
  // { robot_id: 'pro', name: 'Sigma 02', model: 'Kachaka S2', status: 'online', battery: 60, x: 220, y: 80, theta: -Math.PI/2, task: '巡邏', color: '#e74c3c', avatar: 'assets/icons/kachaka.png', traj: null },
];


window.addEventListener('DOMContentLoaded', () => {
  assignRobotTrajectories();
  // gen. task cards from robotStatusList 
  tasks = robotStatusList.map((robot, idx) => ({
    // task_id: `task-robot-${idx+1}`,
    task_id: `task-00${idx+1}`,
    robot_id: robot.robot_id,
    status: 'executing',
    steps: [
      { action: 'Follow Path', params: { path: 'custom trajectory' }, status: 'executing' }
    ]
  }));
  if (typeof renderTasks === 'function') renderTasks();
  // Create task button functionality
  const createBtn = document.getElementById('create-task-btn');
  if (createBtn) {
    createBtn.onclick = function() {
      // If Bootstrap Modal component exists, trigger display
      const modal = document.getElementById('editTaskModal');
      if (modal) {
        if (typeof bootstrap !== 'undefined') {
          const modalObj = bootstrap.Modal.getOrCreateInstance(modal);
          modalObj.show();
        } else {
          modal.style.display = 'block'; // fallback
        }
      }
    };
  }

  try {
    renderRobotStatusCards();
    renderRobotMap();
    bindEditTaskModalEvents();
    setInterval(() => {
      simulateRobotStatus(); // 每秒設定新目標點
    }, 1000);
    animateRobotMovement(); // 啟動動畫循環
  } catch(e) {
    alert('Failed to render robot status or map: '+e);
  }
});


function renderRobotStatusCards() {
  const root = document.getElementById('robot-status-cards');
  if (!root) return;
  root.innerHTML = '';
  console.log(robotStatusList);
  robotStatusList.forEach(robot => {
    const card = document.createElement('div');
    card.className = 'card mb-3 shadow-sm';
    card.innerHTML = `
      <div class="card-body p-3">
        <div class="d-flex align-items-center mb-2">
          <img src="${robot.avatar}" alt="avatar" class="me-2" style="width:2.2rem;height:2.2rem;border-radius:50%;background:#fff;border:2px solid #eee;object-fit:cover;">
          <div>
            <span class="fw-bold">${robot.name}</span>
            <span class="text-muted ms-1" style="font-size:0.95rem;">(${robot.robot_id})</span><br>
            <span class="badge bg-light text-dark border me-1" style="font-size:0.8rem;">${robot.model}</span>
            <span class="badge ${robot.status==='online'?'bg-success':(robot.status==='charging'?'bg-info':'bg-secondary')}">
              ${robot.status==='online'?'Online':robot.status==='charging'?'Charging':'Offline'}
            </span>
          </div>
        </div>
        <div class="mb-1">
          <i class="bi bi-lightning-charge"></i>
          <span class="fw-bold">${robot.battery}%</span>
          <div class="progress mt-1" style="height:8px;">
            <div class="progress-bar ${robot.battery>50?'bg-success':(robot.battery>20?'bg-warning':'bg-danger')}" role="progressbar" style="width:${robot.battery}%" aria-valuenow="${robot.battery}" aria-valuemin="0" aria-valuemax="100"></div>
          </div>
        </div>
        <div class="mb-1 small text-muted">
          <i class="bi bi-geo"></i> (${robot.x.toFixed(2)}, ${robot.y.toFixed(2)})
        </div>
        <div class="mb-1">
          <i class="bi bi-list-task"></i> ${robot.task ? robot.task : '<span class="text-muted">無任務</span>'}
        </div>
      </div>
    `;
    root.appendChild(card);
  });
}


function renderRobotMap() {
  const mapDiv = document.getElementById('robot-map');
  if (!mapDiv) return;
  mapDiv.innerHTML = '';
  // --- my_map.png ---
  // const mapImgW = 325, mapImgH = 183;
  // const w = mapDiv.clientWidth || 480;
  // const h = mapDiv.clientHeight || 360;

  // --- vac_map.png ---
  const mapImgW = 1060, mapImgH = 827;
  const w = mapDiv.clientWidth || 1060;
  const h = mapDiv.clientHeight || 827;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.cursor = 'grab';
  mapDiv.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  // Map view state
  let view = {
    tx: w/2 - mapImgW/2, // x offset
    ty: h/2 - mapImgH/2, // y offset
    scale: 1,
    minScale: 0.5,
    maxScale: 5,
    dragging: false,
    lastX: 0,
    lastY: 0
  };

  // Map background image
  const img = new Image();
  img.src = 'vac_map.png'; // Replace with map image
  img.onload = function() {
    draw();
  };

  // Let external code redraw
  mapDiv._robotMapDraw = draw;

  function draw() {
    ctx.save();
    ctx.setTransform(1,0,0,1,0,0);
    ctx.clearRect(0, 0, w, h);
    ctx.translate(view.tx, view.ty);
    ctx.scale(view.scale, view.scale);
    // Draw map
    ctx.drawImage(img, 0, 0, mapImgW, mapImgH);

    // === Draw pathPoints as polyline and points ===
    if (typeof pathPoints !== 'undefined' && pathPoints.length > 1) {
      // Draw lines
      ctx.save();
      ctx.globalAlpha = 0.2;
      ctx.strokeStyle = '#0099ff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(pathPoints[0].x, pathPoints[0].y);
      for (let i=1; i<pathPoints.length; ++i) {
        ctx.lineTo(pathPoints[i].x, pathPoints[i].y);
      }
      ctx.stroke();
      // Draw points
      for (let i=0; i<pathPoints.length; ++i) {
        ctx.beginPath();
        ctx.arc(pathPoints[i].x, pathPoints[i].y, 4, 0, 2*Math.PI);
        ctx.fillStyle = '#ff8800';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      ctx.globalAlpha = 1.0;
      ctx.restore();
    }

    // draw rectangle at (575, 160) with width 80 and height 30, with filled color light blue in opacity 0.5
    // text 'pick up 1' at the center of the rectangle
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = '#0099ff';
    ctx.fillRect(575, 160, 80, 30);
    ctx.restore();
    ctx.save();
    ctx.font = '16px Arial';
    ctx.fillStyle = '#000';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('pick up 1', 615, 175);
    ctx.restore();

    // draw rectangle at (550, 100) with width 20 and height 50, with filled color light red in opacity 0.5
    // text 'pick up 2' at the center of the rectangle
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = '#ff0000';
    ctx.fillRect(550, 100, 20, 50);
    ctx.restore();
    ctx.save();
    ctx.font = '16px Arial';
    ctx.fillStyle = '#000';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('pick up 2', 555, 125);
    ctx.restore();

    // draw rectangle at (550, 470) with width 50 and height 20, with filled color light green in opacity 0.5
    // text 'pick up 3' at the center of the rectangle
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = '#00ff00';
    ctx.fillRect(550, 470, 50, 20);
    ctx.restore();
    ctx.save();
    ctx.font = '16px Arial';
    ctx.fillStyle = '#000';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('pick up 3', 575, 480);
    ctx.restore();

    // --- draw robots ---
    robotStatusList.forEach(robot => {
      ctx.save();
      ctx.translate(robot.x, robot.y);
      ctx.rotate(robot.theta || 0);
      // Draw robot sprite
      let sprite = new Image();
      sprite.src = robot.avatar;
      sprite.onload = function() {
        // Only redraw once when first loaded
      }

      // --- If sprite is not loaded, draw a circle ---
      if (sprite.complete) {
        ctx.drawImage(sprite, -8, -5, 16, 10);
      } else {
        ctx.beginPath();
        ctx.arc(0, 0, 10, 0, 2*Math.PI);
        ctx.fillStyle = robot.color + (robot.status === 'online' ? '' : '55');
        ctx.fill();
        ctx.strokeStyle = '#222';
        ctx.stroke();
      }
      ctx.restore();
    });
    ctx.restore();
  }

  // --- Mouse drag to pan ---
  canvas.addEventListener('mousedown', (e) => {
    view.dragging = true;
    view.lastX = e.clientX;
    view.lastY = e.clientY;
    canvas.style.cursor = 'grabbing';
  });
  window.addEventListener('mousemove', (e) => {
    if (view.dragging) {
      const dx = e.clientX - view.lastX;
      const dy = e.clientY - view.lastY;
      view.tx += dx;
      view.ty += dy;
      view.lastX = e.clientX;
      view.lastY = e.clientY;
      draw();
    }
  });
  window.addEventListener('mouseup', () => {
    view.dragging = false;
    canvas.style.cursor = 'grab';
  });

  // --- Mouse wheel to zoom ---
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const mouseX = e.offsetX;
    const mouseY = e.offsetY;
    // Convert mouse coordinates to map coordinates
    const mapX = (mouseX - view.tx) / view.scale;
    const mapY = (mouseY - view.ty) / view.scale;
    let scale = view.scale * (e.deltaY < 0 ? 1.1 : 0.9);
    scale = Math.max(view.minScale, Math.min(view.maxScale, scale));
    // Keep the point under the mouse cursor unchanged
    view.tx = mouseX - mapX * scale;
    view.ty = mouseY - mapY * scale;
    view.scale = scale;
    draw();
  }, { passive: false });

  // --- Double click to reset view ---
  canvas.addEventListener('dblclick', () => {
    view.tx = w/2 - mapImgW/2;
    view.ty = h/2 - mapImgH/2;
    view.scale = 1;
    draw();
  });
}

// Let external code redraw the map when data changes (e.g. simulateRobotStatus updates)
function redrawRobotMapOnly() {
  const mapDiv = document.getElementById('robot-map');
  if (mapDiv && typeof mapDiv._robotMapDraw === 'function') {
    mapDiv._robotMapDraw();
  }
}


function simulateRobotStatus() {
  // --- Only simulate battery, no longer generate target points ---
  robotStatusList.forEach(robot => {
    if(robot.status==='online') {
      robot.battery = Math.max(0, Math.min(100, robot.battery + Math.round(Math.random()*4-2)));
    }
  });
  renderRobotStatusCards();
}

// --- Assign trajectories to robots ---
// ====== 手繪軌跡定義（可自訂）======
// 範例：一個不規則閉合路徑（座標陣列，需首尾相連）
const pathPoints = [
  {x: 170, y: 75}, {x: 240, y: 65}, {x: 250, y: 110}, {x: 160, y: 110}, {x: 100, y: 150}, {x: 95, y: 90}, {x: 120, y: 70}, {x: 170, y: 75}
];
// ====== 軌跡分配 ======
function assignRobotTrajectories() {
  const N = robotStatusList.length;
  // 計算路徑長度表與總長
  let totalLen = 0;
  const segLens = [];
  for (let i = 1; i < pathPoints.length; ++i) {
    const dx = pathPoints[i].x - pathPoints[i-1].x;
    const dy = pathPoints[i].y - pathPoints[i-1].y;
    const len = Math.hypot(dx, dy);
    segLens.push(len);
    totalLen += len;
  }
  // 均勻分布每台機器人於路徑上
  robotStatusList.forEach((robot, i) => {
    robot.traj = {
      pathPoints,
      segLens,
      totalLen,
      offset: (i/N) * totalLen, // 每台 phase 均勻分布
      speed: totalLen / (60*1) // 5倍變慢, 60秒繞一圈
    };
    robot.t = 0; // t: 已走的距離
  });
}

// --- Animation loop ---
function animateRobotMovement() {
  let needRedraw = false;
  const dt = 1/60;
  robotStatusList.forEach(robot => {
    if(robot.status==='online' && robot.traj && robot.traj.pathPoints) {
      // ---沿手繪路徑等速推進---
      const {pathPoints, segLens, totalLen, offset, speed} = robot.traj;
      let dist = (robot.t + speed*dt) % totalLen;
      robot.t = dist;
      // ---加上 phase offset---
      let curDist = (dist + offset) % totalLen;
      // ---找到目前在第幾段---
      let segIdx = 0, accLen = 0;
      while (segIdx < segLens.length && accLen + segLens[segIdx] < curDist) {
        accLen += segLens[segIdx];
        segIdx++;
      }
      // ---線段內插---
      const p0 = pathPoints[segIdx];
      const p1 = pathPoints[segIdx+1];
      const segLen = segLens[segIdx];
      const segT = segLen ? (curDist - accLen) / segLen : 0;
      robot.x = p0.x + (p1.x - p0.x) * segT;
      robot.y = p0.y + (p1.y - p0.y) * segT;
      // heading 取切線方向
      robot.theta = Math.atan2(p1.y - p0.y, p1.x - p0.x);
      needRedraw = true;
    } else if (robot.status==='online' && robot.traj) {
      // --- fallback: Lissajous ---
      robot.t = (robot.t + robot.traj.speed*dt) % 1;
      const angle = 2*Math.PI*(robot.t + robot.traj.phase);
      robot.x = robot.traj.cx + robot.traj.ax * Math.sin(robot.traj.kx * angle);
      robot.y = robot.traj.cy + robot.traj.ay * Math.sin(robot.traj.ky * angle);
      const dx = robot.traj.ax * robot.traj.kx * Math.cos(robot.traj.kx * angle);
      const dy = robot.traj.ay * robot.traj.ky * Math.cos(robot.traj.ky * angle);
      robot.theta = Math.atan2(dy, dx);
      needRedraw = true;
    }
  });
  if (needRedraw) redrawRobotMapOnly();
  requestAnimationFrame(animateRobotMovement);
}

// --- Main loop ---
try {
  renderRobotStatusCards();
  renderRobotMap();
  setInterval(() => {
    simulateRobotStatus(); // 每秒設定新目標點
  }, 1000);
  animateRobotMovement(); // 啟動動畫循環
} catch(e) {
  alert('Failed to render robot status or map: '+e);
}
function bindCreateTaskButton() {
  const btn = document.getElementById('create-task-btn');
  if (btn) {
    btn.addEventListener('click', () => openCreateTaskModal());
  }
}

// --- Open create task modal ---
function openCreateTaskModal() {
  fetchRobots(); // <--- Or updateRobotSelects()
  document.getElementById('edit-task-id').value = '';
  document.getElementById('edit-robot-select').value = '';
  document.getElementById('edit-task-steps-list').innerHTML = '';
  addEditStepRow(); // Add default empty step
  updateTaskJsonPreview();
  const modal = new bootstrap.Modal(document.getElementById('editTaskModal'));
  modal.show();
}

// Fetch tasks
function fetchTasks() {
  fetch('/api/tasks')
    .then(res => res.json())
    .then(data => {
      tasks = data;
      renderTasks();
    });
}

function fetchRobots(statusFilter = 'online') {
  // Fetch robots and filter by status
  const filteredRobots = robotStatusList.filter(robot => robot.status === statusFilter);
  robots = filteredRobots;
  updateRobotSelects();
}

function updateRobotSelects() {
  const selectElement = document.getElementById('edit-robot-select');
  if (!selectElement) return;
  selectElement.innerHTML = '<option value="">請選擇機器人</option>'; // Reset options
  robots.forEach(robot => {
    const option = document.createElement('option');
    option.value = robot.robot_id;
    option.textContent = `${robot.name} (${robot.model})`;
    selectElement.appendChild(option);
  });
}

// Render tasks table
function renderTasks() {
  // const tbody = document.getElementById('active-tasks-list');
  const tbody = document.getElementById('task-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';
  if (!tasks.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No tasks</td></tr>';
    return;
  }
  tasks.forEach(task => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${task.task_id}</td>
      <td>${task.robot_id || '-'}</td>
      <td>${task.status}</td>
      <td><div class="progress" style="height:8px;"><div class="progress-bar bg-info" style="width:${task.steps ? Math.round(100 * task.steps.filter(s=>s.status==="success").length/task.steps.length) : 0}%"></div></div></td>
      <td>
        <button class="btn btn-sm btn-outline-danger cancel-task-btn" data-task-id="${task.task_id}"><i class="bi bi-x"></i></button>
      </td>
    `;
    tbody.appendChild(tr);
  });
  // Bind create task button
  const createBtn = document.getElementById('create-task-btn');
  if (createBtn) {
    createBtn.addEventListener('click', () => openEditTaskModal());
  }
  // Bind cancel task buttons
  const cancelButtons = document.querySelectorAll('.cancel-task-btn');
  cancelButtons.forEach(button => {
    button.addEventListener('click', (e) => {
      const taskId = e.currentTarget.dataset.taskId;
      cancelTask(taskId);
    });
  });
}

// Update all robot selects
function updateRobotSelects() {
  const selectElement = document.getElementById('edit-robot-select');
  if (!selectElement) return;
  selectElement.innerHTML = '<option value="">請選擇機器人</option>'; // Reset options
  robots.forEach(robot => {
    const option = document.createElement('option');
    option.value = robot.robot_id;
    option.textContent = `${robot.name} (${robot.model})`;
    selectElement.appendChild(option);
  });
}

// --- Bind modal events ---
function bindEditTaskModalEvents() {
  // Add step button
  const addStepBtn = document.getElementById('add-step-btn');
  if (addStepBtn) {
    addStepBtn.addEventListener('click', () => {
      addEditStepRow();
      updateTaskJsonPreview();
    });
  }
  // --- Update JSON preview when any field changes ---
  document.getElementById('edit-robot-select').addEventListener('change', updateTaskJsonPreview);
  document.getElementById('edit-task-steps-list').addEventListener('input', updateTaskJsonPreview);
  // --- Submit form ---
  const form = document.getElementById('edit-task-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      submitEditTask();
    });
  }
}

// --- Update JSON preview in real-time ---
function updateTaskJsonPreview() {
  const robotId = document.getElementById('edit-robot-select').value;
  const status = 'queued';
  const steps = Array.from(document.querySelectorAll('#edit-task-steps-list .input-group')).map(div => {
    const action = div.querySelector('.step-action').value;
    let params = {};
    try {
      params = JSON.parse(div.querySelector('.step-params').value || '{}');
    } catch(e) {
      params = {};
    }
    const stepStatus = div.querySelector('.step-status').value;
    return { action, params, status: stepStatus };
  });
  const jsonObj = {
    robot_id: robotId,
    status,
    steps
  };
  document.getElementById('task-json-preview').value = JSON.stringify(jsonObj, null, 2);
}

// Open edit modal and populate data
function openEditTaskModal(taskId) {
  fetchRobots(); // <--- Or updateRobotSelects()
  const task = tasks.find(t => t.task_id === taskId);
  if (!task) return;
  document.getElementById('edit-task-id').value = task.task_id;
  document.getElementById('edit-robot-select').value = task.robot_id || '';
  // Steps
  const stepsList = document.getElementById('edit-task-steps-list');
  stepsList.innerHTML = '';
  (task.steps || []).forEach((step, idx) => {
    addEditStepRow(step, idx);
  });
  // Show Modal (Bootstrap 5)
  const modal = new bootstrap.Modal(document.getElementById('editTaskModal'));
  modal.show();
}

// Add a new step row
function addEditStepRow(step = {}, idx = null) {
  const stepsList = document.getElementById('edit-task-steps-list');
  const div = document.createElement('div');
  div.className = 'input-group mb-2';
  div.innerHTML = `
    <input type="text" class="form-control step-action" placeholder="動作 (action)" value="${step.action||''}" required>
    <input type="text" class="form-control step-params" placeholder="參數 (JSON)" value='${step.params ? JSON.stringify(step.params) : ''}'>
    <select class="form-select step-status">
      <option value="pending" ${step.status==="pending"?'selected':''}>待處理</option>
      <option value="executing" ${step.status==="executing"?'selected':''}>執行中</option>
      <option value="success" ${step.status==="success"?'selected':''}>成功</option>
      <option value="fail" ${step.status==="fail"?'selected':''}>失敗</option>
    </select>
    <button type="button" class="btn btn-danger btn-lg remove-step-btn ms-2" title="刪除步驟"><i class="bi bi-trash"></i></button>
  `;
  stepsList.appendChild(div);
  div.querySelector('.remove-step-btn').addEventListener('click', () => {
    div.remove();
    updateTaskJsonPreview();
  });
}

// --- Submit edited task ---
function submitEditTask() {
  const taskId = document.getElementById('edit-task-id').value;
  const robotId = document.getElementById('edit-robot-select').value;
  const status = 'queued';
  const steps = Array.from(document.querySelectorAll('#edit-task-steps-list .input-group')).map(div => {
    const action = div.querySelector('.step-action').value;
    let params = {};
    try {
      params = JSON.parse(div.querySelector('.step-params').value || '{}');
    } catch(e) {
      params = {};
    }
    const stepStatus = div.querySelector('.step-status').value;
    return { action, params, status: stepStatus };
  });

  const taskData = {
    task_id: taskId || `task-${Date.now()}`,
    robot_id: robotId,
    status,
    steps
  };

  // --- Fake data mode: only operate the frontend tasks array
  if (taskId) {
    // Edit task
    const idx = tasks.findIndex(t => t.task_id === taskId);
    if (idx !== -1) {
      tasks[idx] = taskData;
    }
  } else {
    // --- Add new task ---
    tasks.push(taskData);
  }

  // TODO: send task data by API to robot

  renderTasks();
  bootstrap.Modal.getInstance(document.getElementById('editTaskModal')).hide();
}

function cancelTask(taskId) {
  const taskIndex = tasks.findIndex(task => task.task_id === taskId);
  if (taskIndex === -1) return;

  tasks.splice(taskIndex, 1); // Remove task from the list
  renderTasks(); // Re-render the task list

  // TODO: send cancel task command by API to robot
}


const gMapDesc = {
  w: 1060,
  h: 827,
  origin:{
    x: -29.4378,  // TBC: the sign of x and y should be checked
    y: -26.3988 
  },
  resolution: 0.05,
}

// =================================
//     Coordinates Transfomation     
// =================================
function tfROS2Canvas(_mapDesc, _rosPos) {
	if (_mapDesc === undefined) { console.error('Map meta-data is not ready!'); return {}; }
	if (!(_mapDesc.hasOwnProperty('h'))) { console.error('Height of map is not defined!'); return {}; }
	if (!("origin" in _mapDesc)) { console.error('Origin of map is not loaded!'); return {}; }

	var xRosOffset = _mapDesc.origin.x / _mapDesc.resolution;
	var yRosOffset = _mapDesc.origin.y / _mapDesc.resolution;

	var xCanvas = (_rosPos.x / _mapDesc.resolution - xRosOffset).toFixed(4);
	var yCanvas = (_rosPos.y / _mapDesc.resolution - yRosOffset);
	yCanvas = (_mapDesc.h - yCanvas).toFixed(4);

	return {
		x: xCanvas,
		y: yCanvas
	};
}

function tfCanvas2ROS(_mapDesc, _cvsPos) {
	if (_mapDesc.h === undefined) { console.error('Height of map is not defined!'); }

	var xRosOffset = _mapDesc.origin.x / _mapDesc.resolution;
	var yRosOffset = _mapDesc.origin.y / _mapDesc.resolution;

	var xRos = ((Number(_cvsPos.x) + Number(xRosOffset)) * _mapDesc.resolution).toFixed(4);
	var yRos = ((Number(_mapDesc.h) - Number(_cvsPos.y) + Number(yRosOffset)) * _mapDesc.resolution).toFixed(4);

	return {
		x: xRos,
		y: yRos
	};
}
