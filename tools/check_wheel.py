"""Check the distribution rather than assuming an editable checkout is enough."""

import email
import zipfile
from pathlib import Path

wheel = next(Path("dist").glob("turbo_whisper-1.1.0-*.whl"))
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
    metadata = email.message_from_bytes(archive.read(metadata_name))
    assert metadata["Name"] == "turbo-whisper"
    assert metadata["Version"] == "1.1.0"
    for module in ("ui", "window", "sessions", "polish", "writer", "writer_helper"):
        assert f"turbo_whisper/{module}.py" in names
    for name in names:
        if name.endswith(".py"):
            compile(archive.read(name), name, "exec")
    entry_points = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
    assert "turbo-whisper = turbo_whisper.main:main" in archive.read(entry_points).decode()
print(f"Verified {wheel}")
