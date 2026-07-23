#!/usr/bin/env bash
set -e

REPO="Nantaphat-Yoktaworn/macfind"
BRANCH="main"
DEST="$HOME/.local/bin"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found on PATH. Install it with your distro's package manager (e.g. sudo apt install python3), then re-run this installer."
    exit 1
fi

mkdir -p "$DEST"
curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/macfind.py" -o "$DEST/macfind.py"

for name in macfind mf; do
    cat > "$DEST/$name" <<WRAPPER
#!/usr/bin/env bash
exec python3 "$DEST/macfind.py" "\$@"
WRAPPER
    chmod +x "$DEST/$name"
done

if [ ! -f "$DEST/devices.json" ]; then
    curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/devices.example.json" -o "$DEST/devices.json"
fi

echo "macfind installed to $DEST"
case ":$PATH:" in
    *":$DEST:"*)
        echo "Run: mf help" ;;
    *)
        echo "$DEST is not on your PATH. Add this to ~/.bashrc or ~/.zshrc, then reopen your shell:"
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo "Then run: mf help" ;;
esac
