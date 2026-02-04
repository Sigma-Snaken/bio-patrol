// Unified Mock Data Configuration
// This file centralizes all fake/mock data used throughout the application
// Making it easy to switch between mock and real data from backend APIs

// =============================================================================
// CONFIGURATION
// =============================================================================

const MOCK_CONFIG = {
  // Enable/disable mock data globally
  enabled: false,
  
  // Simulation mode settings
  simulation: {
    enabled: false,
    robotAnimationSpeed: 1.0,
    pathUpdateInterval: 100
  }
};

// =============================================================================
// MAP AND LOCATION DATA
// =============================================================================

const MOCK_MAP_DATA = {
  // Map description for coordinate transformations
  description: {
    width: 1060,
    height: 827,
    origin: {
      x: -29.4378,
      y: -26.3988 
    },
    resolution: 0.05
  },
  
  // Room definitions with precise overlay coordinates
  rooms: [
    {id: 103, x: 42, y: 365, width: 85, height: 140, name: "Room 103"},
    {id: 102, x: 141, y: 365, width: 85, height: 140, name: "Room 102"},
    {id: 101, x: 270, y: 365, width: 85, height: 140, name: "Room 101"},
    {id: 114, x: 715, y: 365, width: 85, height: 140, name: "Room 114"},
    {id: 113, x: 815, y: 365, width: 85, height: 140, name: "Room 113"},
    {id: 112, x: 948, y: 365, width: 85, height: 140, name: "Room 112"},
    {id: 104, x: 42, y: 540, width: 85, height: 140, name: "Room 104"},
    {id: 105, x: 141, y: 540, width: 85, height: 140, name: "Room 105"},
    {id: 106, x: 270, y: 540, width: 85, height: 140, name: "Room 106"},
    {id: 107, x: 410, y: 635, width: 85, height: 140, name: "Room 107"},
    {id: 108, x: 580, y: 635, width: 85, height: 140, name: "Room 108"},
    {id: 109, x: 715, y: 540, width: 85, height: 140, name: "Room 109"},
    {id: 110, x: 815, y: 540, width: 85, height: 140, name: "Room 110"},
    {id: 111, x: 948, y: 540, width: 85, height: 140, name: "Room 111"}
  ],
  
  // Predefined locations (navigation waypoints)
  locations: [
    'B_101-1', 'B_102-1', 'B_103-1', 'B_104-1', 'B_105-1', 'B_106-1', 
    'B_107-1', 'B_108-1', 'B_109-1', 'B_110-1', 'B_111-1', 'B_112-1', 
    'B_113-1', 'B_114-1'
  ],
  
  // Shelf identifiers
  shelves: ['S_01', 'S_02', 'S_03']
};

// =============================================================================
// ROBOT DATA
// =============================================================================

const MOCK_ROBOT_DATA = {
  // Robot fleet configuration
  fleet: [
    {
      id: 'normal',
      name: 'Sigma 01',
      model: 'Kachaka S1',
      status: 'idle', // idle, online, busy, charging, error
      battery: 100,
      position: {
        x: 0,
        y: 0,
        theta: 0
      },
      task: null,
      color: '#4e73df',
      avatar: 'assets/icons/kachaka.png',
      capabilities: ['navigation', 'bio_measurement', 'patrol'],
      last_seen: new Date().toISOString()
    },
    {
      id: 'pro',
      name: 'Sigma 02', 
      model: 'Kachaka S2',
      status: 'charging',
      battery: 65,
      position: {
        x: 220,
        y: 80,
        theta: -Math.PI/2
      },
      task: null,
      color: '#e74c3c',
      avatar: 'assets/icons/kachaka.png',
      capabilities: ['navigation', 'patrol'],
      last_seen: new Date().toISOString()
    }
  ],
  
  // Dynamic robot status updates (for simulation)
  statusUpdates: {
    batteryDecayRate: 0.1, // % per minute
    positionNoiseRange: 0.5,
    statusTransitions: {
      'idle': ['busy', 'charging'],
      'busy': ['idle', 'error'],
      'charging': ['idle'],
      'error': ['idle']
    }
  }
};

// =============================================================================
// TASK DATA
// =============================================================================

const MOCK_TASK_DATA = {
  // Task templates
  templates: {
    bio_measurement: {
      task_type: 'bio_measurement',
      priority: 'high',
      estimated_duration: 300, // seconds
      steps: [
        {
          step_id: 1,
          action: 'navigate_to_location',
          parameters: {
            location_id: null // to be filled
          },
          status: 'pending',
          estimated_duration: 60
        },
        {
          step_id: 2,
          action: 'measure_bio_data',
          parameters: {
            measurement_type: 'vital_signs',
            duration: 30,
            retry_attempts: 3
          },
          status: 'pending',
          estimated_duration: 120
        }
      ]
    },
    
    patrol: {
      task_type: 'patrol',
      priority: 'medium',
      estimated_duration: 600,
      steps: [
        {
          step_id: 1,
          action: 'follow_path',
          parameters: {
            path_id: 'patrol_route_1'
          },
          status: 'pending',
          estimated_duration: 600
        }
      ]
    },
    
    navigation: {
      task_type: 'navigation',
      priority: 'medium', 
      estimated_duration: 180,
      steps: [
        {
          step_id: 1,
          action: 'navigate_to_location',
          parameters: {
            location_id: null // to be filled
          },
          status: 'pending',
          estimated_duration: 180
        }
      ]
    }
  },
  
  // Sample task instances
  sampleTasks: [
    {
      task_id: 'task-001',
      robot_id: 'normal',
      status: 'executing',
      created_at: new Date().toISOString(),
      task_type: 'bio_measurement',
      steps: [
        {
          step_id: 1,
          action: 'navigate_to_location',
          parameters: { location_id: 'B_101-1' },
          status: 'completed'
        },
        {
          step_id: 2,
          action: 'measure_bio_data',
          parameters: { room_id: '101', bed_id: '1' },
          status: 'executing'
        }
      ]
    }
  ]
};

// =============================================================================
// SENSOR DATA
// =============================================================================

const MOCK_SENSOR_DATA = {
  // Bio-sensor measurement scenarios
  scenarios: {
    success_first: {
      attempts: 1,
      final_status: 1,
      data: {
        bpm: () => Math.floor(Math.random() * (80 - 60 + 1)) + 60,
        rpm: () => Math.floor(Math.random() * (20 - 12 + 1)) + 12,
        temperature: () => +(36.2 + Math.random() * 1.4).toFixed(1),
        signal_quality: () => +(0.8 + Math.random() * 0.2).toFixed(2),
        is_valid: true
      }
    },
    
    success_retry: {
      attempts: 3,
      final_status: 1,
      data: {
        bpm: () => Math.floor(Math.random() * (90 - 55 + 1)) + 55,
        rpm: () => Math.floor(Math.random() * (25 - 10 + 1)) + 10,
        temperature: () => +(36.0 + Math.random() * 1.6).toFixed(1),
        signal_quality: () => +(0.6 + Math.random() * 0.4).toFixed(2),
        is_valid: true
      }
    },
    
    all_fail: {
      attempts: 5,
      final_status: 4,
      data: {
        bpm: 0,
        rpm: 0,
        temperature: 0,
        signal_quality: () => +(Math.random() * 0.3).toFixed(2),
        is_valid: false
      }
    }
  },
  
  // Historical scan data generator
  generateScanHistory: (count = 100) => {
    const scenarios = Object.keys(MOCK_SENSOR_DATA.scenarios);
    const history = [];
    
    for (let i = 0; i < count; i++) {
      const scenarioName = scenarios[Math.floor(Math.random() * scenarios.length)];
      const scenario = MOCK_SENSOR_DATA.scenarios[scenarioName];
      const taskId = `bio-task-${String(i + 1).padStart(6, '0')}`;
      
      // Generate data for each retry attempt
      for (let attempt = 0; attempt < scenario.attempts; attempt++) {
        const data = {};
        Object.keys(scenario.data).forEach(key => {
          if (typeof scenario.data[key] === 'function') {
            data[key] = scenario.data[key]();
          } else {
            data[key] = scenario.data[key];
          }
        });
        
        history.push({
          id: `${taskId}_${attempt + 1}`,
          task_id: taskId,
          timestamp: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
          retry_count: attempt + 1,
          status: attempt + 1 === scenario.attempts ? scenario.final_status : 2,
          ...data,
          data_json: JSON.stringify(data)
        });
      }
    }
    
    return history.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }
};

// =============================================================================
// PATH AND TRAJECTORY DATA  
// =============================================================================

const MOCK_PATH_DATA = {
  // Simulation trajectory points
  simulated_paths: {
    patrol_route_1: [
      {x: 170, y: 75}, {x: 240, y: 65}, {x: 250, y: 110}, 
      {x: 160, y: 110}, {x: 100, y: 150}, {x: 95, y: 90}, 
      {x: 120, y: 70}, {x: 170, y: 75}
    ],
    
    simple_path: [
      {x: 0, y: 0}, {x: 1, y: 1}, {x: 3.5, y: 1}, 
      {x: 2, y: 0}, {x: 0, y: 0}
    ]
  },
  
  // Generate random path
  generateRandomPath: (startPoint, endPoint, waypoints = 3) => {
    const path = [startPoint];
    
    for (let i = 0; i < waypoints; i++) {
      const t = (i + 1) / (waypoints + 1);
      const x = startPoint.x + (endPoint.x - startPoint.x) * t + (Math.random() - 0.5) * 20;
      const y = startPoint.y + (endPoint.y - startPoint.y) * t + (Math.random() - 0.5) * 20;
      path.push({x, y});
    }
    
    path.push(endPoint);
    return path;
  }
};

// =============================================================================
// API RESPONSE TEMPLATES
// =============================================================================

const MOCK_API_RESPONSES = {
  // Success response template
  success: (data, message = 'Operation successful') => ({
    status: 'success',
    message,
    data,
    timestamp: new Date().toISOString()
  }),
  
  // Error response template
  error: (message, code = 'UNKNOWN_ERROR', details = null) => ({
    status: 'error',
    message,
    error_code: code,
    details,
    timestamp: new Date().toISOString()
  }),
  
  // Robot status response
  robotStatus: (robotId) => {
    const robot = MOCK_ROBOT_DATA.fleet.find(r => r.robot_id === robotId);
    if (!robot) {
      return MOCK_API_RESPONSES.error(`Robot ${robotId} not found`, 'ROBOT_NOT_FOUND');
    }
    return MOCK_API_RESPONSES.success(robot);
  },
  
  // Task creation response
  taskCreated: (taskData) => ({
    status: 'success',
    message: 'Task created successfully',
    data: {
      ...taskData,
      task_id: taskData.task_id || `task-${Date.now()}`,
      created_at: new Date().toISOString(),
      status: 'pending'
    }
  })
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

const MockDataUtils = {
  // Get mock data based on type
  getMockData: (type, params = {}) => {
    switch (type) {
      case 'robots':
        return MOCK_ROBOT_DATA.fleet;
      case 'robot':
        return MOCK_ROBOT_DATA.fleet.find(r => r.robot_id === params.robotId);
      case 'tasks':
        return MOCK_TASK_DATA.sampleTasks;
      case 'locations':
        return MOCK_MAP_DATA.locations;
      case 'shelves':
        return MOCK_MAP_DATA.shelves;
      case 'rooms':
        return MOCK_MAP_DATA.rooms;
      case 'sensorHistory':
        return MOCK_SENSOR_DATA.generateScanHistory(params.count);
      default:
        return null;
    }
  },
  
  // Create task from template
  createTaskFromTemplate: (templateName, params = {}) => {
    const template = MOCK_TASK_DATA.templates[templateName];
    if (!template) return null;
    
    return {
      ...template,
      task_id: `task-${Date.now()}`,
      robot_id: params.robot_id,
      created_at: new Date().toISOString(),
      status: 'pending',
      steps: template.steps.map(step => ({
        ...step,
        parameters: { ...step.parameters, ...params.stepParams }
      }))
    };
  },
  
  // Simulate API delay
  simulateDelay: (ms = 500) => new Promise(resolve => setTimeout(resolve, ms)),
  
  // Check if mock mode is enabled
  isMockMode: () => MOCK_CONFIG.enabled
};

// =============================================================================
// EXPORT
// =============================================================================

// Global exposure for browser usage
if (typeof window !== 'undefined') {
  window.MockData = {
    config: MOCK_CONFIG,
    map: MOCK_MAP_DATA,
    robots: MOCK_ROBOT_DATA,
    tasks: MOCK_TASK_DATA,
    sensors: MOCK_SENSOR_DATA,
    paths: MOCK_PATH_DATA,
    api: MOCK_API_RESPONSES,
    utils: MockDataUtils
  };
}

// Export for Node.js usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    MOCK_CONFIG,
    MOCK_MAP_DATA,
    MOCK_ROBOT_DATA,
    MOCK_TASK_DATA,
    MOCK_SENSOR_DATA,
    MOCK_PATH_DATA,
    MOCK_API_RESPONSES,
    MockDataUtils
  };
}