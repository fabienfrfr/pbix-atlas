import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pbix_atlas.cli import main


def test_main_no_args():
    with pytest.raises(SystemExit):
        main([])


def test_main_missing_file():
    rc = main(["/nonexistent/file.pbix"])
    assert rc == 1


def test_main_output_default():
    with tempfile.NamedTemporaryFile(suffix=".pbix", delete=False) as f:
        p = Path(f.name)
    p.write_text("dummy")
    with patch("pbix_atlas.cli.generate_python_pipeline") as mock_gen:
        mock_gen.return_value = Path("out.py")
        rc = main([str(p)])
        assert rc == 0
    p.unlink()


def test_main_output_custom():
    with tempfile.NamedTemporaryFile(suffix=".pbix", delete=False) as f:
        p = Path(f.name)
    p.write_text("dummy")
    out = tempfile.NamedTemporaryFile(suffix=".py", delete=False)
    out_path = Path(out.name)
    with patch("pbix_atlas.cli.generate_python_pipeline") as mock_gen:
        mock_gen.return_value = out_path
        rc = main([str(p), "-o", str(out_path)])
        assert rc == 0
    p.unlink()
    if out_path.exists():
        out_path.unlink()


def test_main_help():
    with pytest.raises(SystemExit):
        main(["--help"])


def test_module_has_main():
    from pbix_atlas import cli
    assert hasattr(cli, "main")
