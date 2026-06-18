#!/usr/bin/env bash
# setup.sh — Fresh antiX Debian VM bootstrap
set -euo pipefail

echo "============================================"
echo "  vm_tools — Fresh antiX VM Setup"
echo "============================================"
echo ""
echo "Before running this script, complete these steps on your HOST machine:"
echo ""
echo "  VirtualBox:"
echo "    1. Settings → Network → Adapter 1 → Attached to: NAT"
echo "       → Advanced → Port Forwarding → Add two rules:"
echo "         Name: SSH   Protocol: TCP   Host Port: 2222   Guest Port: 22"
echo "         Name: APP   Protocol: TCP   Host Port: 8000   Guest Port: 8000"
echo "    3. After SSH is enabled you can connect from host with:"
echo "         ssh -p 2222 <your-user>@127.0.0.1"
echo ""
echo "  VMware:"
echo "    1. Settings → Network Adapter → NAT"
echo "       Edit → Virtual Network Editor → NAT Settings → Port Forwarding:"
echo "         SSH: host 2222 → guest 22"
echo "         APP: host 8000 → guest 8000"
echo ""
echo "  NOTE — If you cloned this VM and want to run both simultaneously,"
echo "  the clone needs different HOST ports to avoid conflicts."
echo ""
read -rp "Press Enter when you have completed the above steps..."
echo ""

# ── Guest Additions ───────────────────────────
echo "[1/8] Installing VirtualBox Guest Additions (for better resolution & performance)..."

sudo apt-get update -qq
sudo apt-get install -y build-essential dkms linux-headers-$(uname -r)

echo ""
echo ">>> IMPORTANT: On your HOST machine, do this now:"
echo "    1. With the VM running, go to VirtualBox menu → Devices → Insert Guest Additions CD Image..."
echo "    2. Then come back here and press Enter..."
read -rp "Press Enter after inserting Guest Additions CD..."

sudo mkdir -p /mnt/cdrom
sudo mount /dev/cdrom /mnt/cdrom 2>/dev/null || echo "Warning: Could not mount CD. Please insert Guest Additions from host."

if [ -f /mnt/cdrom/VBoxLinuxAdditions.run ]; then
    echo "Installing Guest Additions..."
    sudo sh /mnt/cdrom/VBoxLinuxAdditions.run --nox11
    echo "Guest Additions installed successfully."
else
    echo "Warning: Guest Additions CD not found. Please insert it from VirtualBox menu and run this script again."
fi

sudo umount /mnt/cdrom 2>/dev/null || true
echo "      Done."
echo ""

# ── Package index ─────────────────────────────
echo "[2/8] Updating apt package index..."
sudo apt-get update -qq
echo "      Done."
echo ""

# ── SSH ───────────────────────────────────────
echo "[3/8] Installing and enabling SSH server..."
sudo apt-get install -y openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
echo "      SSH is running. Connect from host: ssh -p 2222 <user>@127.0.0.1"
echo ""

# ── Chromium ──────────────────────────────────
echo "[4/8] Installing Chromium browser and setting it as default..."
sudo apt-get install -y chromium

# Set Chromium as default browser
xdg-settings set default-web-browser chromium.desktop
xdg-mime default chromium.desktop x-scheme-handler/http
xdg-mime default chromium.desktop x-scheme-handler/https
xdg-mime default chromium.desktop text/html

echo "      Chromium installed and set as default browser."
echo ""

# ── System deps ───────────────────────────────
echo "[5/8] Installing Python build dependencies, tkinter, and clipboard tools..."
sudo apt-get install -y \
  python3-tk python3-dev \
  build-essential libssl-dev zlib1g-dev \
  libncurses5-dev libncursesw5-dev libreadline-dev \
  libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev \
  libexpat1-dev liblzma-dev tk-dev libffi-dev \
  xclip xsel
echo "      Done."
echo ""

# ── Python 3.13 ───────────────────────────────
PY_VERSION="3.13.5"
PY_BIN="python${PY_VERSION%.*}"   # python3.13

echo "[6/8] Checking for Python $PY_VERSION..."
if command -v "$PY_BIN" &>/dev/null && "$PY_BIN" --version 2>&1 | grep -q "$PY_VERSION"; then
  echo "      Python $PY_VERSION already installed — skipping build."
else
  echo "      Python $PY_VERSION not found. Building from source (this takes a few minutes)..."
  cd /tmp
  echo "      Downloading Python-${PY_VERSION}.tgz..."
  wget -q "https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tgz"
  echo "      Extracting..."
  tar xf "Python-${PY_VERSION}.tgz"
  cd "Python-${PY_VERSION}"
  echo "      Configuring..."
  ./configure --enable-optimizations --with-ensurepip=install -q
  echo "      Compiling (using $(nproc) cores)..."
  make -j"$(nproc)"
  echo "      Installing..."
  sudo make altinstall
  cd /tmp
  rm -rf "Python-${PY_VERSION}" "Python-${PY_VERSION}.tgz"
  echo "      Python $PY_VERSION installed successfully."
fi
echo ""

# ── Repo check ────────────────────────────────
REPO_DIR="$HOME/vm_tools"

echo "[7/8] Checking for repo at $REPO_DIR..."
if [ ! -d "$REPO_DIR" ]; then
  echo ""
  echo "  [!] $REPO_DIR not found."
  echo "      Copy your repo to the VM first, then re-run this script."
  echo "      From your host machine run:"
  echo "        scp -P 2222 -r ./vm_tools <user>@127.0.0.1:~/"
  exit 1
fi
echo "      Repo found."
echo ""

# ── DISPLAY env var ───────────────────────────
echo "[7.5/8] Setting DISPLAY=:0 in ~/.bashrc..."
grep -qxF 'export DISPLAY=:0' ~/.bashrc || echo 'export DISPLAY=:0' >> ~/.bashrc
export DISPLAY=:0
echo "      Done."
echo ""

# ── Venv + dependencies ───────────────────────
echo "[8/8] Setting up Python virtual environment and installing dependencies..."
cd "$REPO_DIR"
echo "      Creating venv..."
"$PY_BIN" -m venv venv
echo "      Activating venv..."
source venv/bin/activate
echo "      Upgrading pip..."
pip install --upgrade pip -q
echo "      Installing requirements.txt..."
pip install -r requirements.txt -q
echo "      Done."
echo ""

echo "============================================"
echo "  Setup complete!"
echo ""
echo "  Next steps after reboot:"
echo "    1. Reboot the VM: sudo reboot"
echo "    2. After reboot, go to VirtualBox menu → View → Auto-resize Guest Display"
echo "    3. You can now change resolution inside the VM easily."
echo ""
echo "  To start the scraper:"
echo "    cd $REPO_DIR"
echo "    source venv/bin/activate"
echo "    python scraper.py"
echo "  Then open: http://127.0.0.1:8000"
echo "============================================"