"""Build a bootable ISO with exported cloud data baked in."""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

HELPER_SCRIPT = Path(__file__).parent / "iso_helper.sh"
# Fallback for installed location
HELPER_SCRIPT_INSTALLED = Path("/opt/openfactory/cloud-scraper/iso-helper.sh")


class LiveEnvironment:
    """Detected live-boot environment info."""

    def __init__(self):
        self.distro: str = "unknown"  # "ubuntu" | "fedora" | "unknown"
        self.is_live: bool = False
        self.source_device: Path | None = None
        self.mount_point: Path | None = None


class IsoBuilder:
    """Bakes exported data into a bootable ISO image.

    Args:
        export_dir: Directory containing exported cloud data.
        progress_cb: Callback(fraction, message) for progress updates.
    """

    def __init__(self, export_dir: Path, progress_cb: Callable[[float, str], None]):
        self._export_dir = export_dir
        self._progress = progress_cb

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_live_environment(self) -> LiveEnvironment:
        """Detect whether we're running in a live CD environment."""
        env = LiveEnvironment()

        try:
            cmdline = Path("/proc/cmdline").read_text()
        except OSError:
            return env

        if "boot=casper" in cmdline:
            env.distro = "ubuntu"
            env.is_live = True
            medium = Path("/run/live/medium")
            if medium.is_dir():
                env.mount_point = medium
                env.source_device = self._find_backing_device(medium)
        elif "rd.live.image" in cmdline:
            env.distro = "fedora"
            env.is_live = True
            live_dir = Path("/run/initramfs/live")
            if live_dir.is_dir():
                env.mount_point = live_dir
                env.source_device = self._find_backing_device(live_dir)

        return env

    def build_iso(self, source_iso: Path, output_iso: Path) -> None:
        """Build a new ISO with exported data injected.

        Args:
            source_iso: Path to the original ISO image.
            output_iso: Path where the new ISO will be written.

        Raises:
            RuntimeError: If any step fails.
        """
        if not source_iso.is_file():
            raise RuntimeError(f"Source ISO not found: {source_iso}")

        if not any(self._export_dir.iterdir()):
            raise RuntimeError(f"Export directory is empty: {self._export_dir}")

        work_dir = Path(tempfile.mkdtemp(prefix="cloud-iso-"))
        iso_dir = work_dir / "iso"

        try:
            # Step 1: Extract ISO
            self._progress(0.05, "Extracting ISO...")
            self._extract_iso(source_iso, iso_dir)

            # Step 2: Detect ISO type
            distro = self._detect_iso_type(iso_dir)
            self._progress(0.15, f"Detected {distro} ISO")

            # Step 3: Create data squashfs
            self._progress(0.20, "Creating data layer...")
            squashfs_path = self._create_data_squashfs(work_dir)

            # Step 4: Inject data
            if distro == "ubuntu":
                self._progress(0.50, "Injecting data layer (casper)...")
                self._inject_ubuntu_layer(iso_dir, squashfs_path)
            elif distro == "fedora":
                self._progress(0.50, "Injecting data into rootfs...")
                self._inject_fedora_data(iso_dir, work_dir)
            else:
                raise RuntimeError(
                    f"Unsupported ISO type. Expected Ubuntu (casper/) or "
                    f"Fedora (LiveOS/) layout."
                )

            # Step 5: Rebuild ISO
            self._progress(0.75, "Rebuilding ISO image...")
            self._rebuild_iso(iso_dir, output_iso, source_iso)

            self._progress(1.0, f"ISO created: {output_iso.name}")

        finally:
            # Clean up work directory
            self._progress(0.95, "Cleaning up...")
            self._run_privileged(
                ["cleanup", str(work_dir)],
                "Cleaning up temporary files",
            )

    # ------------------------------------------------------------------
    # Internal — ISO manipulation
    # ------------------------------------------------------------------

    def _detect_iso_type(self, iso_dir: Path) -> str:
        """Detect whether the extracted ISO is Ubuntu or Fedora."""
        if (iso_dir / "casper").is_dir():
            return "ubuntu"
        if (iso_dir / "LiveOS").is_dir():
            return "fedora"
        return "unknown"

    def _extract_iso(self, iso_path: Path, dest: Path) -> None:
        """Extract ISO contents using xorriso."""
        dest.mkdir(parents=True, exist_ok=True)
        self._run_privileged(
            ["extract-iso", str(iso_path), str(dest)],
            "Extracting ISO contents",
        )

    def _create_data_squashfs(self, work_dir: Path) -> Path:
        """Create a squashfs image containing the exported data.

        The data is placed at /cloud-export/ inside the squashfs.
        """
        staging = work_dir / "staging" / "cloud-export"
        staging.mkdir(parents=True, exist_ok=True)

        # Copy export data into staging area
        for item in self._export_dir.iterdir():
            dest = staging / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        output = work_dir / "cloud-data.squashfs"
        self._run_privileged(
            ["create-squashfs", str(work_dir / "staging"), str(output)],
            "Creating data squashfs layer",
        )
        return output

    def _inject_ubuntu_layer(self, iso_dir: Path, squashfs: Path) -> None:
        """Add data squashfs as a casper overlay layer.

        Casper discovers layers by dot-separated naming. We find the
        top existing layer and add ours with an additional segment.
        """
        casper_dir = iso_dir / "casper"
        if not casper_dir.is_dir():
            raise RuntimeError("casper/ directory not found in ISO")

        # Find existing squashfs layers
        layers = sorted(casper_dir.glob("*.squashfs"))
        if not layers:
            raise RuntimeError("No squashfs layers found in casper/")

        # Use the longest name (most segments = top layer) as base
        top_layer = max(layers, key=lambda p: len(p.stem.split(".")))
        # Add our segment: e.g. minimal.standard.live.squashfs ->
        # minimal.standard.live.cloud-data.squashfs
        base_stem = top_layer.stem
        new_name = f"{base_stem}.cloud-data.squashfs"
        dest = casper_dir / new_name

        shutil.copy2(squashfs, dest)
        log.info("Injected Ubuntu layer: %s", new_name)

    def _inject_fedora_data(self, iso_dir: Path, work_dir: Path) -> None:
        """Inject data into Fedora's rootfs.img inside squashfs.img."""
        liveos_dir = iso_dir / "LiveOS"
        squashfs_img = liveos_dir / "squashfs.img"
        if not squashfs_img.is_file():
            raise RuntimeError("LiveOS/squashfs.img not found in ISO")

        unsquash_dir = work_dir / "unsquash"
        mount_point = work_dir / "rootfs_mount"
        mount_point.mkdir(parents=True, exist_ok=True)

        try:
            # Unsquash the outer squashfs
            self._run_privileged(
                ["unsquash", str(squashfs_img), str(unsquash_dir)],
                "Extracting squashfs.img",
            )

            rootfs_img = unsquash_dir / "squashfs-root" / "LiveOS" / "rootfs.img"
            if not rootfs_img.is_file():
                raise RuntimeError("LiveOS/rootfs.img not found inside squashfs")

            # Mount rootfs.img
            self._run_privileged(
                ["mount-rootfs", str(rootfs_img), str(mount_point)],
                "Mounting rootfs.img",
            )

            # Copy data into /cloud-export/
            cloud_dir = mount_point / "cloud-export"
            self._run_privileged(
                ["mkdir-p", str(cloud_dir)],
                "Creating /cloud-export/ in rootfs",
            )
            for item in self._export_dir.iterdir():
                dest = cloud_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            # Unmount
            self._run_privileged(
                ["umount-rootfs", str(mount_point)],
                "Unmounting rootfs.img",
            )

            # Recreate squashfs.img
            new_squashfs = work_dir / "new-squashfs.img"
            self._run_privileged(
                [
                    "create-squashfs",
                    str(unsquash_dir / "squashfs-root"),
                    str(new_squashfs),
                ],
                "Recreating squashfs.img",
            )

            # Replace original
            shutil.copy2(new_squashfs, squashfs_img)

        finally:
            # Best-effort unmount in case of error
            try:
                self._run_privileged(
                    ["umount-rootfs", str(mount_point)],
                    "Cleanup unmount",
                )
            except RuntimeError:
                pass

    def _rebuild_iso(
        self, iso_dir: Path, output: Path, original: Path
    ) -> None:
        """Rebuild ISO image preserving boot records."""
        self._run_privileged(
            ["rebuild-iso", str(iso_dir), str(output), str(original)],
            "Rebuilding ISO image",
        )

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _find_backing_device(self, mount_point: Path) -> Path | None:
        """Find the block device backing a mount point."""
        try:
            result = subprocess.run(
                ["findmnt", "-n", "-o", "SOURCE", str(mount_point)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    def _get_helper_script(self) -> str:
        """Return the path to the helper script."""
        if HELPER_SCRIPT.is_file():
            return str(HELPER_SCRIPT)
        if HELPER_SCRIPT_INSTALLED.is_file():
            return str(HELPER_SCRIPT_INSTALLED)
        raise RuntimeError(
            "iso_helper.sh not found. Expected at "
            f"{HELPER_SCRIPT} or {HELPER_SCRIPT_INSTALLED}"
        )

    def _run_privileged(self, args: list[str], desc: str) -> None:
        """Run iso_helper.sh via pkexec for privileged operations."""
        helper = self._get_helper_script()
        cmd = ["pkexec", helper] + args

        log.info("Running privileged: %s — %s", " ".join(args), desc)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min max
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Operation timed out: {desc}")
        except OSError as e:
            raise RuntimeError(f"Failed to run pkexec: {e}")

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "dismissed" in stderr.lower() or result.returncode == 126:
                raise RuntimeError("Authorization was cancelled by user")
            raise RuntimeError(
                f"{desc} failed (exit {result.returncode}): {stderr}"
            )

    def copy_live_iso(self, env: LiveEnvironment, work_dir: Path) -> Path:
        """Copy the ISO from the live medium to a working location.

        Args:
            env: Detected live environment.
            work_dir: Directory to copy the ISO into.

        Returns:
            Path to the copied ISO file.
        """
        if not env.mount_point:
            raise RuntimeError("No live medium mount point found")

        # Look for .iso file on the medium
        iso_files = list(env.mount_point.glob("*.iso"))
        if iso_files:
            src = iso_files[0]
            dest = work_dir / src.name
            self._progress(0.02, f"Copying {src.name} from live medium...")
            shutil.copy2(src, dest)
            return dest

        # For optical media, dd from the source device
        if env.source_device and env.source_device.is_block_device():
            dest = work_dir / "source.iso"
            self._progress(0.02, "Copying ISO from optical drive...")
            self._run_privileged(
                ["dd-device", str(env.source_device), str(dest)],
                "Copying from optical drive",
            )
            return dest

        raise RuntimeError(
            "Could not locate source ISO on live medium. "
            "Please select an ISO file manually."
        )
