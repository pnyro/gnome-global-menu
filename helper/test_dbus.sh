#!/bin/bash
# Test script for Global Menu D-Bus service
# Run this while the service (globalmenu_service.py) is running

set -e

BUS_NAME="org.gnome.GlobalMenu"
OBJECT_PATH="/org/gnome/GlobalMenu"
INTERFACE="org.gnome.GlobalMenu"

echo "========================================================================"
echo "  Testing Global Menu D-Bus Service"
echo "========================================================================"
echo ""

# Check if service is running
echo "1. Checking if service is running..."
if gdbus introspect --session --dest $BUS_NAME --object-path $OBJECT_PATH &>/dev/null; then
    echo "   ✅ Service is running"
else
    echo "   ❌ Service is NOT running!"
    echo "      Start it with: python3 globalmenu_service.py"
    exit 1
fi
echo ""

# Introspect the service
echo "2. Introspecting D-Bus interface..."
echo ""
gdbus introspect --session --dest $BUS_NAME --object-path $OBJECT_PATH
echo ""

# Get current menu
echo "3. Getting current menu (switch to a window with a menubar like GIMP)..."
echo ""
MENU_JSON=$(gdbus call --session --dest $BUS_NAME --object-path $OBJECT_PATH --method $INTERFACE.GetCurrentMenu)

# Extract the JSON string (remove D-Bus wrapping)
MENU_JSON=$(echo "$MENU_JSON" | sed "s/^('\(.*\)',)$/\1/" | sed 's/\\n/\n/g')

echo "Raw response:"
echo "$MENU_JSON"
echo ""

# Pretty print with jq if available
if command -v jq &>/dev/null; then
    echo "Formatted menu structure:"
    echo "$MENU_JSON" | jq '.'
else
    echo "(Install 'jq' for pretty JSON formatting: sudo dnf install jq)"
fi
echo ""

# Get statistics
echo "4. Getting service statistics..."
STATS=$(gdbus call --session --dest $BUS_NAME --object-path $OBJECT_PATH --method $INTERFACE.GetStatistics)
echo "   $STATS"
echo ""

# Monitor signals
echo "5. Monitoring MenuChanged signals (switch between windows)..."
echo "   Press Ctrl+C to stop monitoring"
echo ""

gdbus monitor --session --dest $BUS_NAME --object-path $OBJECT_PATH

echo ""
echo "========================================================================"
echo "  Test complete!"
echo "========================================================================"
