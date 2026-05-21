import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.backup import detect_drives, create_backup


def test_detect_drives_parses_proc_mounts(tmp_path):
    fake_mounts = """\
sysfs /sys sysfs rw 0 0
proc /proc proc rw 0 0
/dev/sda3 /run/media/user/Linux Half 2TB ext4 rw 0 0
/dev/nvme0n1p2 / ext4 rw 0 0
tmpfs /tmp tmpfs rw 0 0
/dev/sda4 /mnt/data ext4 rw 0 0
"""
    mounts_file = tmp_path / "mounts"
    mounts_file.write_text(fake_mounts)

    with patch("scripts.backup.MOUNTS_FILE", str(mounts_file)):
        with patch("scripts.backup.shutil.disk_usage") as mock_du:
            mock_du.return_value = MagicMock(free=10 * 1024**3)
            drives = detect_drives()

    paths = [d["path"] for d in drives]
    assert "/mnt/data" in paths
    assert "/run/media/user/Linux Half 2TB" in paths
    # System/virtual mounts excluded
    assert "/" not in paths
    assert "/sys" not in paths
    assert "/tmp" not in paths


def test_detect_drives_sorted_by_free_space(tmp_path):
    fake_mounts = """\
/dev/sda3 /mnt/small ext4 rw 0 0
/dev/sda4 /mnt/large ext4 rw 0 0
"""
    mounts_file = tmp_path / "mounts"
    mounts_file.write_text(fake_mounts)

    def fake_du(path):
        return MagicMock(free=1 * 1024**3 if "small" in path else 100 * 1024**3)

    with patch("scripts.backup.MOUNTS_FILE", str(mounts_file)):
        with patch("scripts.backup.shutil.disk_usage", side_effect=fake_du):
            drives = detect_drives()

    assert drives[0]["path"] == "/mnt/large"


def test_create_backup_calls_tar(tmp_path):
    home_dir = tmp_path / "home" / "user"
    home_dir.mkdir(parents=True)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    # Force the single-threaded path to keep this test environment-independent
    with patch("scripts.backup._find_pigz", return_value=None):
        with patch("scripts.backup.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("scripts.backup.Path.stat") as mock_stat:
                mock_stat.return_value = MagicMock(st_size=5 * 1024**3)
                result = create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "tar"
    assert "czf" in cmd
    assert any("2026-05-20" in arg for arg in cmd)
    assert str(home_dir) in cmd
    assert result["compressor"] == "gzip"
    assert result["threads"] == 1


def test_create_backup_raises_on_tar_failure(tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="No space left")
        with pytest.raises(RuntimeError, match="tar failed"):
            create_backup(str(home_dir), str(tmp_path / "backup"), date_str="2026-05-20")


def test_create_backup_rejects_destination_inside_home(tmp_path):
    """Backing up into a subdir of home would loop the growing archive into itself."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    inside = home_dir / "backups"
    inside.mkdir()
    with pytest.raises(ValueError, match="inside home"):
        create_backup(str(home_dir), str(inside), date_str="2026-05-20")


def test_create_backup_rejects_destination_equal_to_home(tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    with pytest.raises(ValueError, match="home directory itself"):
        create_backup(str(home_dir), str(home_dir), date_str="2026-05-20")


def test_create_backup_uses_separator_to_block_arg_injection(tmp_path):
    """`tar` argv must use -- before the path to prevent filename-as-option."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("scripts.backup.Path.stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=1024)
            create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    cmd = mock_run.call_args[0][0]
    assert "--" in cmd
    # The home_dir argument must come AFTER --
    assert cmd.index("--") < cmd.index(str(home_dir))


def test_create_backup_includes_default_excludes(tmp_path):
    """Common cache/junk paths must be excluded by default."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("scripts.backup.Path.stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=1024)
            create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    cmd = mock_run.call_args[0][0]
    joined = " ".join(cmd)
    assert ".cache" in joined
    assert "node_modules" in joined
    assert "Trash" in joined


def test_create_backup_passes_timeout(tmp_path):
    """subprocess.run must be called with a timeout."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("scripts.backup.Path.stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=1024)
            create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    assert "timeout" in mock_run.call_args.kwargs
    assert mock_run.call_args.kwargs["timeout"] > 0


def test_create_backup_one_file_system_flag(tmp_path):
    """tar must not cross filesystem boundaries (avoids backing up /mnt mounts)."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("scripts.backup.Path.stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=1024)
            create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    cmd = mock_run.call_args[0][0]
    assert "--one-file-system" in cmd


def test_create_backup_uses_pigz_when_available(tmp_path):
    """When pigz is on PATH, tar -I 'pigz -p N' is used (parallel compression)."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup._find_pigz", return_value="/usr/bin/pigz"):
        with patch("scripts.backup.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("scripts.backup.Path.stat") as mock_stat:
                mock_stat.return_value = MagicMock(st_size=1024)
                result = create_backup(
                    str(home_dir), str(backup_dir),
                    date_str="2026-05-20", threads=8,
                )

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "tar"
    assert "-I" in cmd
    i_idx = cmd.index("-I")
    # tar -I argument is a shell-style program spec
    assert "pigz" in cmd[i_idx + 1]
    assert "-p 8" in cmd[i_idx + 1]
    # czf is NOT used in the pigz path
    assert "czf" not in cmd
    assert result["compressor"] == "pigz"
    assert result["threads"] == 8


def test_create_backup_defaults_threads_to_cpu_count(tmp_path):
    """When threads is not specified, defaults to os.cpu_count()."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup._find_pigz", return_value="/usr/bin/pigz"):
        with patch("scripts.backup.os.cpu_count", return_value=12):
            with patch("scripts.backup.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch("scripts.backup.Path.stat") as mock_stat:
                    mock_stat.return_value = MagicMock(st_size=1024)
                    result = create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    cmd = mock_run.call_args[0][0]
    i_idx = cmd.index("-I")
    assert "-p 12" in cmd[i_idx + 1]
    assert result["threads"] == 12


def test_create_backup_falls_back_to_gzip_when_pigz_missing(tmp_path):
    """Without pigz, single-threaded gzip via tar czf is used."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup._find_pigz", return_value=None):
        with patch("scripts.backup.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("scripts.backup.Path.stat") as mock_stat:
                mock_stat.return_value = MagicMock(st_size=1024)
                result = create_backup(
                    str(home_dir), str(backup_dir),
                    date_str="2026-05-20", threads=16,
                )

    cmd = mock_run.call_args[0][0]
    assert "czf" in cmd
    assert "-I" not in cmd
    assert result["compressor"] == "gzip"
    # threads field reflects what was actually used (1 for single-threaded gzip)
    assert result["threads"] == 1


def test_create_backup_pigz_threads_clamped_to_minimum_1(tmp_path):
    """threads=0 or negative must coerce to a sensible default."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    with patch("scripts.backup._find_pigz", return_value="/usr/bin/pigz"):
        with patch("scripts.backup.os.cpu_count", return_value=4):
            with patch("scripts.backup.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                with patch("scripts.backup.Path.stat") as mock_stat:
                    mock_stat.return_value = MagicMock(st_size=1024)
                    result = create_backup(
                        str(home_dir), str(backup_dir),
                        date_str="2026-05-20", threads=0,
                    )

    assert result["threads"] == 4  # fell back to cpu_count()
