# PyMOL + claudemol Troubleshooting

## Connection Issues

### Connection Refused (Port 9880)

**Symptom:**
```
ConnectionRefusedError: [Errno 111] Connection refused
socket.error: [Errno 61] Connection refused
```

**Causes and Solutions:**

1. **PyMOL not running**
   - Start PyMOL before attempting to connect
   - The claudemol plugin only listens when PyMOL is running

2. **Plugin not loaded**
   - Run `claudemol setup` to install the plugin
   - Restart PyMOL after setup
   - Check PyMOL startup messages for plugin errors

3. **Firewall blocking**
   - Allow localhost connections on port 9880
   - Check system firewall settings

4. **Wrong port**
   - Default port is 9880
   - Verify port in claudemol configuration

**Diagnostic commands:**
```bash
# Check if port is listening (macOS/Linux)
lsof -i :9880

# Check if port is listening (Windows)
netstat -an | findstr 9880

# Test connection
python -c "import socket; s=socket.socket(); s.connect(('localhost', 9880)); print('Connected')"
```

### Port Already in Use

**Symptom:**
```
OSError: [Errno 48] Address already in use
```

**Solution:**
```bash
# Find process using port
lsof -i :9880

# Kill process (replace PID)
kill -9 <PID>
```

### Timeout Errors

**Symptom:**
```
socket.timeout: timed out
```

**Causes:**
- PyMOL is processing a long operation
- Large structure loading
- Ray tracing in progress

**Solutions:**
- Increase socket timeout
- Wait for PyMOL to finish current operation
- Use `cmd.sync()` between commands

```python
sock.settimeout(120)  # 2 minutes
```

## Platform-Specific Issues

### macOS

#### GLUT/OpenGL Errors with pip

**Symptom:**
```
ImportError: cannot import name 'GLUT' from 'OpenGL'
dyld: Library not loaded: libGL.1.dylib
```

**Cause:**
The pip-installed PyMOL (`pymol-open-source`) may lack OpenGL/GLUT dependencies on macOS.

**Solution:**
Install PyMOL via Homebrew instead:
```bash
pip uninstall pymol-open-source
brew install pymol
```

#### Permission Denied for Plugin Directory

**Symptom:**
```
PermissionError: [Errno 13] Permission denied
```

**Solution:**
```bash
# Fix permissions
chmod -R u+w ~/Library/Application\ Support/pymol
```

### Windows

#### No GUI Window (Headless Mode)

**Symptom:**
PyMOL runs but no window appears when installed via pip.

**Cause:**
The `pymol-open-source` pip package on Windows runs in headless mode.

**Solutions:**

1. **Use headless mode (for scripting/rendering)**
   - This is actually fine for claudemol
   - Commands and rendering work without GUI
   - Use `cmd.png()` to save images

2. **Install licensed PyMOL**
   - Download from https://pymol.org/
   - Full GUI support
   - Run `claudemol setup` after installation

3. **Use Conda**
   ```bash
   conda install -c conda-forge pymol-open-source
   ```

#### Missing Visual C++ Redistributable

**Symptom:**
```
DLL load failed: The specified module could not be found
```

**Solution:**
Install Visual C++ Redistributable:
https://aka.ms/vs/17/release/vc_redist.x64.exe

### Linux

#### Display/X11 Errors

**Symptom:**
```
Error: Unable to open display
cannot open display
```

**Causes:**
- No X11 server running
- Incorrect DISPLAY variable
- Running in SSH without X forwarding

**Solutions:**

1. **Local display**
   ```bash
   export DISPLAY=:0
   ```

2. **SSH with X forwarding**
   ```bash
   ssh -X user@host
   ```

3. **Headless rendering (Xvfb)**
   ```bash
   xvfb-run pymol -c script.py
   ```

4. **Wayland issues**
   ```bash
   export GDK_BACKEND=x11
   ```

#### Missing System Libraries

**Symptom:**
```
ImportError: libGL.so.1: cannot open shared object file
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt install libgl1-mesa-glx libglu1-mesa

# Fedora
sudo dnf install mesa-libGL mesa-libGLU

# Arch
sudo pacman -S mesa glu
```

## Plugin Issues

### Plugin Not Loading

**Symptom:**
PyMOL starts but claudemol plugin doesn't load (port 9880 not listening).

**Diagnostic:**
Check PyMOL startup messages in terminal.

**Solutions:**

1. **Re-run setup**
   ```bash
   claudemol setup
   ```

2. **Check plugin file**
   ```bash
   # macOS
   ls ~/Library/Application\ Support/pymol/startup/

   # Linux
   ls ~/.pymol/startup/

   # Windows
   dir %APPDATA%\pymol\startup\
   ```

3. **Manual plugin installation**
   Create `claudemol_startup.py` in PyMOL startup directory:
   ```python
   import claudemol
   claudemol.start_server()
   ```

### Plugin Conflicts

**Symptom:**
claudemol conflicts with other PyMOL plugins.

**Solution:**
- Check startup directory for conflicting plugins
- Try renaming other plugins temporarily
- Report conflict to claudemol maintainers

## Command Execution Issues

### Commands Not Executing

**Symptom:**
Socket connection works but commands don't execute.

**Causes:**
- Invalid Python/PyMOL syntax
- Missing imports
- Object/selection doesn't exist

**Solutions:**

1. **Check syntax**
   ```python
   # Use cmd.* functions
   cmd.fetch('1ubq')  # Correct
   fetch 1ubq  # Wrong - this is PyMOL command line syntax
   ```

2. **Verify objects exist**
   ```python
   cmd.get_names()  # List loaded objects
   ```

### Large Response Issues

**Symptom:**
Responses truncated or connection drops with large outputs.

**Solution:**
```python
# Increase buffer size
response = sock.recv(65536)  # 64KB

# Or read in chunks
chunks = []
while True:
    chunk = sock.recv(4096)
    if not chunk:
        break
    chunks.append(chunk)
response = b''.join(chunks)
```

## Performance Issues

### Slow Ray Tracing

**Symptoms:**
- Ray tracing takes very long
- System becomes unresponsive

**Solutions:**

1. **Reduce resolution**
   ```python
   cmd.ray(800, 600)  # Smaller image
   ```

2. **Lower quality settings**
   ```python
   cmd.set('antialias', 0)
   cmd.set('ray_trace_mode', 0)
   ```

3. **Simplify scene**
   ```python
   cmd.hide('surface', 'all')  # Surfaces are expensive
   cmd.hide('(hydro)')  # Hide hydrogens
   ```

### Memory Issues

**Symptom:**
PyMOL crashes or becomes unresponsive with large structures.

**Solutions:**
- Close unused objects: `cmd.delete('old_structure')`
- Use lower surface quality: `cmd.set('surface_quality', 0)`
- Process structures in batches

## Verification Checklist

Run this checklist to verify your installation:

```bash
# 1. Check claudemol installed
python -c "import claudemol; print('claudemol OK')"

# 2. Check PyMOL available
pymol --version || python -c "import pymol; print('pymol OK')"

# 3. Start PyMOL (in separate terminal)
pymol &

# 4. Test port (after PyMOL starts)
python -c "import socket; s=socket.socket(); s.connect(('localhost', 9880)); print('Port OK'); s.close()"

# 5. Test command
python -c "
import socket, json
s = socket.socket()
s.connect(('localhost', 9880))
s.send(json.dumps({'code': 'print(\"Hello from claudemol\")'}).encode())
print(s.recv(4096).decode())
s.close()
"
```

## Getting Help

### Resources
- claudemol GitHub: https://github.com/colorifix/claudemol
- PyMOL Wiki: https://pymolwiki.org/
- PyMOL-users mailing list

### Reporting Issues
When reporting issues, include:
1. Operating system and version
2. Python version
3. PyMOL version and installation method (pip/brew/conda/licensed)
4. claudemol version
5. Complete error message
6. Steps to reproduce
