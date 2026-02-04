# Deployment Guide

## Building Single Executable File

### Quick Build (Windows)
```batch
# Run the batch file
build.bat
```

### Manual Build
```bash
# Install PyInstaller
pip install pyinstaller

# Build single-file executable
python build.py

# Or build directory-based (faster startup)
python build.py --onedir
```

## Deployment

### Single-File Executable
1. Copy `dist/kachaka_cmd_center.exe` to target machine
2. Copy `.env.local` to the same directory as the executable
3. Run the executable

**Directory structure on target machine:**
```
deployment_folder/
├── kachaka_cmd_center.exe
└── .env.local
```

### Directory-Based Executable
1. Copy entire `dist/kachaka_cmd_center/` folder to target machine
2. Copy `.env.local` to the `kachaka_cmd_center/` directory
3. Run `kachaka_cmd_center.exe` from inside the folder

**Directory structure on target machine:**
```
kachaka_cmd_center/
├── kachaka_cmd_center.exe
├── .env.local
├── _internal/
│   └── [many files...]
└── [other bundled files...]
```

## Configuration

### Environment Variables (.env.local)
```ini
# Application Settings
PORT=8000
RELOAD=false

# MQTT Settings
MQTT_BROKER_IP=<MQTT_BROKER_IP>
MQTT_BROKER_PORT=1883
MQTT_TOPIC=data-test/demo/wisleep-eck/org/201906078
MQTT_ENABLED=false
MQTT_CLIENT_ID=kachaka_client
```

### Running the Application
```bash
# Single-file executable
./kachaka_cmd_center.exe

# The application will start on http://localhost:8000
# API docs available at http://localhost:8000/docs
# UI available at http://localhost:8000/ui
```

## System Requirements

### Target Machine Requirements
- **OS**: Windows 10/11
- **Memory**: 256MB RAM minimum
- **Disk**: 100MB free space
- **Network**: Internet connection (if using external APIs)
- **No Python installation required**

### Build Machine Requirements
- Python 3.12+
- PyInstaller 6.15.0+
- All project dependencies installed

## Quick Start

### For End Users
1. Download `kachaka_cmd_center.exe` and `.env.local`
2. Place both files in the same folder
3. run `kachaka_cmd_center.exe`
4. Open http://<HOST_IP>:8000 in your browser

### Example Folder Structure
```
kachaka_deployment/
├── kachaka_cmd_center.exe
├── .env.local
└── start_server.bat (optional helper script)
```

## Auto-run on boot (on Windows)
1. combo `Window` + `R` 
2. enter "shell:startup"
3. Drag and drop the Link(捷徑) of *.exe file to the folder. (eg. C:\Users\<username>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup)

### Data Directory
 * .env.local configuration file
   - C:\Users\<username>\AppData\Local\KachakaCommandCenter\.env.local
 * data/sensor_data.db 
   - C:\Users\<username>\AppData\Local\KachakaCommandCenter\data\sensor_data.db
 * debug logs
   - C:\Users\<username>\AppData\Local\KachakaCommandCenter\logs\kachaka_debug.log 
 


## Troubleshooting

### Common Issues

1. **Executable terminates immediately**
   - Check if `.env.local` is in the same directory as the executable
   - Run from command line to see error messages
   - Use debug version: `kachaka_cmd_center_debug.exe`

2. **"Pydantic validation error"**
   - Fixed in current version - ensure you have the latest build
   - Config classes now ignore extra fields in .env file

3. **Configuration not loading**
   - Verify `.env.local` is in the same directory as executable
   - Check file permissions and content format

4. **Import errors**
   - Add missing modules to `hiddenimports` in spec file
   - Rebuild after adding imports

5. **Slow startup (single-file only)**
   - Normal behavior for single-file executables (5-15 seconds)
   - Use directory-based build for faster startup (1-3 seconds)

### Performance Notes

- **Single-file**: 5-15 second startup, easier distribution
- **Directory-based**: 1-3 second startup, more files to distribute
- **File size**: ~100-200MB depending on dependencies

## Advanced Configuration

### Custom Spec File
Modify `app_onefile.spec` to:
- Add additional data files
- Include/exclude specific modules
- Customize executable properties

### Build Optimization
```bash
# Minimize size with UPX compression
# (already enabled in spec file)

# Debug build for troubleshooting
pyinstaller --debug all app_onefile.spec
```

## Security Considerations

- **Config files**: Don't include sensitive data in bundled files
- **Environment variables**: Use .env.local for configuration
- **Updates**: Replace entire executable for updates
- **Validation**: Test executable on clean machine before deployment