#!/bin/bash

# Test script for Claude Code Token Monitor

echo "🔍 Testing Claude Code Token Monitor Installation"
echo "==============================================="

# Check if monitor is installed
if command -v claude-monitor &> /dev/null; then
    echo "✅ claude-monitor is installed"
    
    # Get version
    echo "📋 Monitor version:"
    claude-monitor --version 2>/dev/null || echo "Version check not available"
    
    # Test basic functionality
    echo ""
    echo "🧪 Testing basic functionality..."
    echo "Running: claude-monitor --help"
    claude-monitor --help
    
    echo ""
    echo "🚀 Monitor is ready to use!"
    echo "To run monitoring:"
    echo "  ./claude-monitor-config.sh"
    echo ""
    echo "Available commands:"
    echo "  claude-monitor                    # Default (Pro plan)"
    echo "  claude-monitor --plan max5        # Max5 plan"
    echo "  claude-monitor --plan max20       # Max20 plan"
    echo "  claude-monitor --reset-hour 3     # Custom reset hour"
    echo "  claude-monitor --timezone US/Eastern  # Custom timezone"
    
else
    echo "❌ claude-monitor not found"
    echo "Please install it with: uv tool install claude-monitor"
fi