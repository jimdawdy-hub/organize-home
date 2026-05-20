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

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("scripts.backup.Path.stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=5 * 1024**3)
            result = create_backup(str(home_dir), str(backup_dir), date_str="2026-05-20")

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "tar"
    assert "czf" in cmd[1]
    assert "2026-05-20" in cmd[2]
    assert str(home_dir) in cmd


def test_create_backup_raises_on_tar_failure(tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    with patch("scripts.backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="No space left")
        with pytest.raises(RuntimeError, match="tar failed"):
            create_backup(str(home_dir), str(tmp_path / "backup"), date_str="2026-05-20")
