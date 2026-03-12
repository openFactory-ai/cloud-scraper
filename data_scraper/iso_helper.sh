#!/bin/bash
# iso_helper.sh — Privileged helper for ISO building operations.
# Invoked via pkexec for a single authentication prompt.
#
# Usage: pkexec iso_helper.sh <command> [args...]
#
# Commands:
#   create-squashfs <source_dir> <output>
#   extract-iso <iso> <workdir>
#   unsquash <squashfs_img> <dest_dir>
#   mount-rootfs <rootfs_img> <mountpoint>
#   umount-rootfs <mountpoint>
#   mkdir-p <path>
#   dd-device <device> <output>
#   rebuild-iso <workdir> <output> <original>
#   cleanup <workdir>

set -euo pipefail

# --- Path validation ---
# All paths must be under /tmp/ or the user's home directory.
validate_path() {
    local p="$1"
    local resolved
    resolved="$(realpath -m "$p" 2>/dev/null || echo "$p")"

    case "$resolved" in
        /tmp/*|/home/*|/run/*)
            return 0
            ;;
        *)
            echo "ERROR: Path not allowed: $resolved (must be under /tmp/, /home/, or /run/)" >&2
            exit 1
            ;;
    esac
}

# Validate a block device path
validate_device() {
    local d="$1"
    if [[ ! -b "$d" ]]; then
        echo "ERROR: Not a block device: $d" >&2
        exit 1
    fi
}

CMD="${1:-}"
shift || true

case "$CMD" in
    create-squashfs)
        # create-squashfs <source_dir> <output>
        [[ $# -eq 2 ]] || { echo "Usage: create-squashfs <source_dir> <output>" >&2; exit 1; }
        SRC="$1"; OUT="$2"
        validate_path "$SRC"
        validate_path "$OUT"
        mksquashfs "$SRC" "$OUT" -comp xz -noappend -quiet
        echo "Created squashfs: $OUT"
        ;;

    extract-iso)
        # extract-iso <iso> <workdir>
        [[ $# -eq 2 ]] || { echo "Usage: extract-iso <iso> <workdir>" >&2; exit 1; }
        ISO="$1"; DEST="$2"
        validate_path "$ISO"
        validate_path "$DEST"
        mkdir -p "$DEST"
        xorriso -osirrox on -indev "$ISO" -extract / "$DEST" 2>/dev/null
        # Make extracted files writable
        chmod -R u+w "$DEST"
        echo "Extracted ISO to: $DEST"
        ;;

    unsquash)
        # unsquash <squashfs_img> <dest_dir>
        [[ $# -eq 2 ]] || { echo "Usage: unsquash <squashfs_img> <dest_dir>" >&2; exit 1; }
        SQ="$1"; DEST="$2"
        validate_path "$SQ"
        validate_path "$DEST"
        mkdir -p "$DEST"
        unsquashfs -d "$DEST/squashfs-root" "$SQ"
        echo "Unsquashed to: $DEST/squashfs-root"
        ;;

    mount-rootfs)
        # mount-rootfs <rootfs_img> <mountpoint>
        [[ $# -eq 2 ]] || { echo "Usage: mount-rootfs <rootfs_img> <mountpoint>" >&2; exit 1; }
        IMG="$1"; MNT="$2"
        validate_path "$IMG"
        validate_path "$MNT"
        mkdir -p "$MNT"
        mount -o loop "$IMG" "$MNT"
        echo "Mounted $IMG at $MNT"
        ;;

    umount-rootfs)
        # umount-rootfs <mountpoint>
        [[ $# -eq 1 ]] || { echo "Usage: umount-rootfs <mountpoint>" >&2; exit 1; }
        MNT="$1"
        validate_path "$MNT"
        if mountpoint -q "$MNT" 2>/dev/null; then
            umount "$MNT"
            echo "Unmounted $MNT"
        else
            echo "Not mounted: $MNT (skipping)"
        fi
        ;;

    mkdir-p)
        # mkdir-p <path>
        [[ $# -eq 1 ]] || { echo "Usage: mkdir-p <path>" >&2; exit 1; }
        DIR="$1"
        validate_path "$DIR"
        mkdir -p "$DIR"
        echo "Created directory: $DIR"
        ;;

    dd-device)
        # dd-device <device> <output>
        [[ $# -eq 2 ]] || { echo "Usage: dd-device <device> <output>" >&2; exit 1; }
        DEV="$1"; OUT="$2"
        validate_device "$DEV"
        validate_path "$OUT"
        dd if="$DEV" of="$OUT" bs=4M status=progress
        echo "Copied device $DEV to $OUT"
        ;;

    rebuild-iso)
        # rebuild-iso <workdir> <output> <original>
        # Rebuilds ISO from extracted directory, preserving boot records.
        [[ $# -eq 3 ]] || { echo "Usage: rebuild-iso <workdir> <output> <original>" >&2; exit 1; }
        WORKDIR="$1"; OUTPUT="$2"; ORIGINAL="$3"
        validate_path "$WORKDIR"
        validate_path "$OUTPUT"
        validate_path "$ORIGINAL"

        # Use xorriso to rebuild, replaying the boot setup from the original
        xorriso -indev "$ORIGINAL" \
            -outdev "$OUTPUT" \
            -boot_image any replay \
            -pathspecs on \
            -map "$WORKDIR" / \
            -volid "CLOUD_DATA" \
            -- 2>/dev/null

        echo "Rebuilt ISO: $OUTPUT"
        ;;

    cleanup)
        # cleanup <workdir>
        [[ $# -eq 1 ]] || { echo "Usage: cleanup <workdir>" >&2; exit 1; }
        WORKDIR="$1"
        validate_path "$WORKDIR"

        # Unmount any loop mounts under workdir
        for mnt in $(findmnt -rn -o TARGET | grep "^${WORKDIR}" | sort -r); do
            umount "$mnt" 2>/dev/null || true
        done

        # Remove work directory
        rm -rf "$WORKDIR"
        echo "Cleaned up: $WORKDIR"
        ;;

    *)
        echo "Unknown command: $CMD" >&2
        echo "Commands: create-squashfs, extract-iso, unsquash, mount-rootfs," >&2
        echo "          umount-rootfs, mkdir-p, dd-device, rebuild-iso, cleanup" >&2
        exit 1
        ;;
esac
