#!/bin/bash

# --- CONFIGURATION ---

# 1. Where are your dotfiles located currently? 
# (Assuming this script is running from inside the dotfiles folder)
DOTFILES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# If your configs are inside a subfolder like 'dotfiles/config', uncomment and edit this:
# DOTFILES_DIR="$DOTFILES_DIR/config"

# 2. Where should they be linked to?
TARGET_DIR="$HOME/.config"

# 3. List of folders to symlink
FOLDERS=(
    "waybar"
    "mako"
    "hyprpaper"
    "hypridle"
    "wlogout"
    "kanshi"
    "walker"
    "swayosd"
    "uwsm"
    "omarchy"
    # "hypr"  <-- Uncomment if you want to include hyprland itself
)

# --- THE LOGIC ---

echo "Starting configuration setup..."
echo "Source: $DOTFILES_DIR"
echo "Target: $TARGET_DIR"
echo "-------------------------------------"

# Create .config directory if it doesn't exist
mkdir -p "$TARGET_DIR"

for folder in "${FOLDERS[@]}"; do
    SOURCE="$DOTFILES_DIR/$folder"
    TARGET="$TARGET_DIR/$folder"

    # Check if the source config actually exists in your dotfiles
    if [ ! -e "$SOURCE" ]; then
        echo "⚠️  WARNING: Could not find '$folder' in your dotfiles. Skipping."
        continue
    fi

    # Check if a folder already exists at the target location
    if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
        # Check if it's already a symlink pointing to the right place
        CURRENT_LINK=$(readlink -f "$TARGET")
        if [ "$CURRENT_LINK" == "$SOURCE" ]; then
            echo "✅ $folder is already correctly linked."
            continue
        fi

        # If it's a real folder or wrong link, back it up
        echo "🔄 Existing config found for $folder. Backing up to $folder.backup..."
        mv "$TARGET" "${TARGET}.backup-$(date +%s)"
    fi

    # Create the symlink
    ln -s "$SOURCE" "$TARGET"
    echo "🔗 Linked: $folder -> $TARGET"

done

echo "-------------------------------------"
echo "Setup complete! Please restart Hyprland to see changes."
