#!/bin/bash
# audit-system.sh
# Comprehensive system audit for Weather Station optimization
# Run as: sudo ./audit-system.sh | tee audit-report.txt

set -e

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

header() { echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"; }
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
metric() { echo -e "  ${YELLOW}►${NC} $1: ${GREEN}$2${NC}"; }

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║         WEATHER STATION SYSTEM AUDIT                         ║"
echo "║         $(date '+%Y-%m-%d %H:%M:%S')                                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"

# ─────────────────────────────────────────────────────────────────────
header "1. HARDWARE IDENTIFICATION"
# ─────────────────────────────────────────────────────────────────────

metric "Model" "$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0' || echo 'Unknown')"
metric "Architecture" "$(uname -m)"
metric "Kernel" "$(uname -r)"
metric "CPU cores" "$(nproc)"
metric "CPU freq (current)" "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null | awk '{print $1/1000 " MHz"}' || echo 'N/A')"
metric "CPU freq (min)" "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null | awk '{print $1/1000 " MHz"}' || echo 'N/A')"
metric "CPU freq (max)" "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null | awk '{print $1/1000 " MHz"}' || echo 'N/A')"
metric "CPU governor" "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'N/A')"
metric "Temperature" "$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 || echo 'N/A')"
metric "Total RAM" "$(free -h | awk '/^Mem:/ {print $2}')"
metric "Available RAM" "$(free -h | awk '/^Mem:/ {print $7}')"

# ─────────────────────────────────────────────────────────────────────
header "2. BOOT TIME ANALYSIS"
# ─────────────────────────────────────────────────────────────────────

info "Overall boot timing:"
systemd-analyze 2>/dev/null || warn "systemd-analyze not available"

echo ""
info "Critical chain to weatherhat.service:"
systemd-analyze critical-chain weatherhat.service 2>/dev/null || warn "weatherhat.service not found"

echo ""
info "Top 20 slowest services:"
systemd-analyze blame 2>/dev/null | head -20

echo ""
info "Services that block boot:"
systemd-analyze critical-chain 2>/dev/null | head -15

# ─────────────────────────────────────────────────────────────────────
header "3. RUNNING SERVICES AUDIT"
# ─────────────────────────────────────────────────────────────────────

info "All enabled services:"
systemctl list-unit-files --state=enabled --type=service --no-pager | grep -v "^UNIT" | sort

echo ""
info "Currently running services:"
systemctl list-units --type=service --state=running --no-pager | grep -v "^UNIT" | head -30

echo ""
info "Failed services:"
systemctl list-units --type=service --state=failed --no-pager 2>/dev/null || echo "  None"

# ─────────────────────────────────────────────────────────────────────
header "4. SERVICES - DISABLE CANDIDATES"
# ─────────────────────────────────────────────────────────────────────

info "Analyzing services that may be unnecessary for headless weather station..."
echo ""

# Check for services that are typically unnecessary on headless IoT
declare -A DISABLE_CANDIDATES=(
    ["avahi-daemon"]="mDNS/Bonjour - only needed for .local discovery"
    ["bluetooth"]="Bluetooth - not used by Weather HAT"
    ["hciuart"]="Bluetooth UART - not used"
    ["triggerhappy"]="Hotkey daemon - no keyboard attached"
    ["console-setup"]="Console fonts - headless system"
    ["keyboard-setup"]="Keyboard config - headless system"
    ["dphys-swapfile"]="Swap file - can cause SD wear"
    ["ModemManager"]="Modem management - no modem"
    ["wpa_supplicant"]="Legacy WiFi - if using NetworkManager"
    ["cups"]="Printing - not needed"
    ["cups-browsed"]="Printer discovery - not needed"
    ["alsa-restore"]="Audio state - no audio"
    ["alsa-state"]="Audio state - no audio"
    ["plymouth"]="Boot splash - headless"
    ["plymouth-start"]="Boot splash - headless"
    ["apt-daily"]="Daily apt updates - manual updates preferred"
    ["apt-daily-upgrade"]="Auto upgrades - manual preferred for stability"
    ["man-db"]="Man page indexing - wastes resources"
    ["e2scrub_all"]="Filesystem scrub - can be scheduled manually"
    ["e2scrub_reap"]="Filesystem scrub cleanup"
    ["udisks2"]="Disk automount - not needed headless"
    ["packagekit"]="Package management GUI backend"
    ["polkit"]="Policy kit - often unneeded headless"
    ["rpi-display-backlight"]="Display backlight - no display"
    ["lightdm"]="Display manager - no display"
    ["xserver"]="X server - no display"
)

for service in "${!DISABLE_CANDIDATES[@]}"; do
    if systemctl is-enabled "$service" 2>/dev/null | grep -q "enabled"; then
        echo -e "  ${RED}●${NC} ${YELLOW}$service${NC} is enabled"
        echo -e "    └─ ${DISABLE_CANDIDATES[$service]}"
    elif systemctl list-unit-files "$service.service" 2>/dev/null | grep -q "$service"; then
        if systemctl is-active "$service" 2>/dev/null | grep -q "^active"; then
            echo -e "  ${YELLOW}●${NC} $service is running (but not enabled)"
        fi
    fi
done

# ─────────────────────────────────────────────────────────────────────
header "5. MEMORY USAGE"
# ─────────────────────────────────────────────────────────────────────

info "Memory overview:"
free -h

echo ""
info "Top 10 memory consumers:"
ps aux --sort=-%mem | head -11 | awk '{printf "  %-6s %-8s %-6s %s\n", $2, $4"%", $6/1024"MB", $11}'

echo ""
info "Swap configuration:"
if swapon --show 2>/dev/null | grep -q .; then
    swapon --show
    warn "Swap is enabled - consider disabling to reduce SD card wear"
else
    echo "  Swap is disabled (good for SD longevity)"
fi

# ─────────────────────────────────────────────────────────────────────
header "6. DISK & FILESYSTEM"
# ─────────────────────────────────────────────────────────────────────

info "Disk usage:"
df -h | grep -E "^/dev|Filesystem"

echo ""
info "Mount options (looking for noatime, ro):"
mount | grep "^/dev" | while read line; do
    device=$(echo "$line" | awk '{print $1}')
    mountpoint=$(echo "$line" | awk '{print $3}')
    options=$(echo "$line" | grep -oP '\(\K[^)]+')
    
    if echo "$options" | grep -q "noatime"; then
        echo -e "  ${GREEN}✓${NC} $mountpoint has noatime"
    else
        echo -e "  ${YELLOW}!${NC} $mountpoint missing noatime (adds unnecessary writes)"
    fi
    
    if echo "$options" | grep -q "\bro\b"; then
        echo -e "  ${GREEN}✓${NC} $mountpoint is read-only"
    else
        echo -e "  ${CYAN}○${NC} $mountpoint is read-write"
    fi
done

echo ""
info "Recent disk I/O (requires root):"
if [ -f /proc/diskstats ]; then
    cat /proc/diskstats | grep -E "mmcblk0 |mmcblk0p" | awk '{print "  " $3 ": reads=" $4 " writes=" $8}'
fi

# ─────────────────────────────────────────────────────────────────────
header "7. NETWORK & WIFI POWER"
# ─────────────────────────────────────────────────────────────────────

info "Network interfaces:"
ip -br addr

echo ""
info "WiFi status:"
iw dev wlan0 info 2>/dev/null || echo "  wlan0 not found"

echo ""
info "WiFi signal strength:"
iw dev wlan0 station dump 2>/dev/null | grep -E "signal|tx bitrate|rx bitrate" | sed 's/^/  /'

echo ""
info "WiFi power management:"
iw dev wlan0 get power_save 2>/dev/null || echo "  Cannot query power save"

echo ""
info "NetworkManager WiFi power saving:"
if command -v nmcli &>/dev/null; then
    nmcli -f WIFI-PROPERTIES dev show wlan0 2>/dev/null | grep -i power || echo "  N/A"
fi

echo ""
info "Checking /etc/NetworkManager/conf.d/ for power settings:"
if [ -d /etc/NetworkManager/conf.d ]; then
    ls -la /etc/NetworkManager/conf.d/ 2>/dev/null || echo "  Empty"
    for f in /etc/NetworkManager/conf.d/*.conf; do
        [ -f "$f" ] && echo "  --- $f ---" && cat "$f"
    done
else
    echo "  Directory not found"
fi

# ─────────────────────────────────────────────────────────────────────
header "8. WEATHER HAT SERVICE STATUS"
# ─────────────────────────────────────────────────────────────────────

info "Service status:"
systemctl status weatherhat --no-pager 2>/dev/null | head -20 || warn "weatherhat service not found"

echo ""
info "Recent logs (last 20 lines):"
journalctl -u weatherhat --no-pager -n 20 2>/dev/null || echo "  No logs available"

echo ""
info "Service resource usage:"
if systemctl is-active weatherhat &>/dev/null; then
    pid=$(systemctl show weatherhat -p MainPID --value)
    if [ "$pid" != "0" ] && [ -n "$pid" ]; then
        ps -p "$pid" -o pid,ppid,%cpu,%mem,rss,vsz,etime,cmd --no-headers 2>/dev/null | awk '{
            printf "  PID: %s\n", $1
            printf "  CPU: %s%%\n", $3
            printf "  Memory: %s%% (%d MB RSS)\n", $4, $5/1024
            printf "  Uptime: %s\n", $7
        }'
    fi
fi

# ─────────────────────────────────────────────────────────────────────
header "9. I2C & GPIO STATUS"
# ─────────────────────────────────────────────────────────────────────

info "I2C devices detected:"
i2cdetect -y 1 2>/dev/null || warn "i2cdetect failed - is I2C enabled?"

echo ""
info "Expected Weather HAT addresses:"
echo "  0x23 - LTR559 (light/proximity)"
echo "  0x48 - ADS1015 (ADC for wind/rain)"
echo "  0x76 or 0x77 - BME280 (temp/humidity/pressure)"

echo ""
info "GPIO chip status:"
if command -v gpioinfo &>/dev/null; then
    gpioinfo 2>/dev/null | head -10
else
    echo "  gpioinfo not available (install gpiod)"
fi

# ─────────────────────────────────────────────────────────────────────
header "10. KERNEL & CONFIG.TXT SETTINGS"
# ─────────────────────────────────────────────────────────────────────

info "Relevant kernel parameters:"
echo "  kernel.printk: $(sysctl -n kernel.printk 2>/dev/null)"
echo "  vm.swappiness: $(sysctl -n vm.swappiness 2>/dev/null)"
echo "  vm.dirty_ratio: $(sysctl -n vm.dirty_ratio 2>/dev/null)"
echo "  vm.dirty_background_ratio: $(sysctl -n vm.dirty_background_ratio 2>/dev/null)"

echo ""
info "config.txt contents (boot configuration):"
CONFIG_TXT=""
[ -f /boot/firmware/config.txt ] && CONFIG_TXT="/boot/firmware/config.txt"
[ -f /boot/config.txt ] && CONFIG_TXT="/boot/config.txt"

if [ -n "$CONFIG_TXT" ]; then
    echo "  Location: $CONFIG_TXT"
    echo ""
    grep -v "^#" "$CONFIG_TXT" | grep -v "^$" | sed 's/^/  /'
else
    warn "config.txt not found"
fi

# ─────────────────────────────────────────────────────────────────────
header "11. SCHEDULED TASKS"
# ─────────────────────────────────────────────────────────────────────

info "System cron jobs:"
for f in /etc/cron.d/*; do
    [ -f "$f" ] && echo "  $f"
done
ls /etc/cron.daily/ 2>/dev/null | sed 's/^/  daily: /'
ls /etc/cron.hourly/ 2>/dev/null | sed 's/^/  hourly: /'
ls /etc/cron.weekly/ 2>/dev/null | sed 's/^/  weekly: /'

echo ""
info "User crontabs:"
crontab -l 2>/dev/null && echo "" || echo "  No crontab for $(whoami)"
sudo -u weather crontab -l 2>/dev/null && echo "" || echo "  No crontab for weather user"

echo ""
info "Systemd timers:"
systemctl list-timers --no-pager | head -15

# ─────────────────────────────────────────────────────────────────────
header "12. OPTIMIZATION SUMMARY"
# ─────────────────────────────────────────────────────────────────────

echo ""
echo "Based on this audit, potential optimizations include:"
echo ""

# Boot time check
boot_time=$(systemd-analyze 2>/dev/null | grep "graphical.target" | grep -oP '\d+\.\d+s' | head -1 | tr -d 's')
if [ -n "$boot_time" ]; then
    if (( $(echo "$boot_time > 30" | bc -l) )); then
        echo -e "  ${RED}●${NC} Boot time is ${boot_time}s - target <20s for solar wake cycles"
    else
        echo -e "  ${GREEN}●${NC} Boot time is ${boot_time}s - acceptable"
    fi
fi

# Swap check
if swapon --show 2>/dev/null | grep -q .; then
    echo -e "  ${YELLOW}●${NC} Disable swap to reduce SD wear: sudo dphys-swapfile swapoff && sudo systemctl disable dphys-swapfile"
fi

# noatime check
if ! mount | grep " / " | grep -q noatime; then
    echo -e "  ${YELLOW}●${NC} Add 'noatime' to root mount options in /etc/fstab"
fi

# WiFi power save
if iw dev wlan0 get power_save 2>/dev/null | grep -q "off"; then
    echo -e "  ${CYAN}●${NC} WiFi power save is OFF - consider enabling for battery life"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Audit complete. Save this output: sudo ./audit-system.sh | tee audit-report.txt"
echo "═══════════════════════════════════════════════════════════════"