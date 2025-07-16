# Claude Code Token Monitor Setup

## ✅ Installation Complete

The Claude Code Token Monitor has been successfully installed and configured for your system.

### 🚀 Quick Start

**Option 1: Interactive Mode**
```bash
# Run with Max20 plan (for Claude Max subscription)
claude-monitor --plan max20

# Run with custom settings
claude-monitor --plan max20 --reset-hour 3 --timezone America/Chicago
```

**Option 2: Using Configuration Script**
```bash
# Run the pre-configured script
./claude-monitor-config.sh
```

**Option 3: Background Monitoring**
```bash
# Start monitor in background
./start-monitor.sh

# View logs
tail -f claude-monitor.log

# Stop monitor
pkill -f claude-monitor
```

### 📋 Available Commands

| Command | Description |
|---------|-------------|
| `claude-monitor` | Default monitoring (Pro plan) |
| `claude-monitor --plan max5` | Max5 plan monitoring |
| `claude-monitor --plan max20` | Max20 plan monitoring (recommended for Claude Max) |
| `claude-monitor --reset-hour 3` | Custom reset hour (3 AM) |
| `claude-monitor --timezone US/Eastern` | Custom timezone |
| `claude-monitor --theme dark` | Dark theme |
| `claude-monitor --refresh-rate 5` | Custom refresh rate (seconds) |

### 🎯 Key Features

- **Real-time Token Tracking**: Monitor your Claude Code token usage in real-time
- **Plan-specific Limits**: Configured for Max20 plan (Claude Max subscription)
- **Timezone Support**: Automatically detects your system timezone
- **Daily Reset**: Tracks daily token limits with 3 AM reset
- **Rich Display**: Color-coded interface with progress bars
- **Background Mode**: Can run continuously in the background

### 📁 Created Files

- `claude-monitor-config.sh` - Main configuration script
- `test-claude-monitor.sh` - Installation test script
- `start-monitor.sh` - Background monitoring script
- `claude-monitor.service` - Systemd service file (optional)
- `claude-monitor.log` - Log file (when running in background)

### 🔧 Configuration

The monitor is pre-configured with:
- **Plan**: Max20 (appropriate for Claude Max subscription)
- **Reset Hour**: 3 AM (avoids peak usage times)
- **Timezone**: Auto-detected from system
- **Refresh Rate**: 10 seconds (default)

### 🛠️ Troubleshooting

**If monitor doesn't start:**
1. Verify installation: `claude-monitor --version`
2. Check PATH: `echo $PATH` should include `/home/stocks/.local/bin`
3. Reinstall if needed: `uv tool install claude-monitor`

**If token data isn't loading:**
- Ensure you have an active Claude Code session
- Check network connectivity
- Verify Claude credentials are valid

### 🏃 Usage Tips

1. **For Development**: Run `claude-monitor --plan max20` in a separate terminal
2. **For Background**: Use `./start-monitor.sh` and check logs periodically
3. **For Debugging**: Add `--debug` flag to any command
4. **For Different Plans**: Adjust `--plan` parameter as needed

### 🔄 Updates

To update the monitor:
```bash
uv tool upgrade claude-monitor
```

## 🎉 Ready to Use!

Your Claude Code Token Monitor is now installed and ready to track your token usage. Start monitoring with:

```bash
./claude-monitor-config.sh
```

Enjoy real-time visibility into your Claude Code token consumption! 🚀