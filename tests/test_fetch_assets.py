"""Offline regression tests for manifest font fetching."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import fetch_assets


class FetchFontsTest(unittest.TestCase):
    def test_archive_member_and_null_sources_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b'font bytes, not the archive bytes'
            archive = root / 'upstream.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('SubsetOTF/JP/Regular.otf', payload)
                z.writestr('other.otf', b'wrong member')
            direct = root / 'upstream.ttf'
            direct.write_bytes(b'direct font')
            fonts = [
                {'id': 'derived', 'source_url': None, 'local_path': 'derived.otf'},
                {'id': 'subset', 'source_url': archive.as_uri(),
                 'source_archive_member': 'SubsetOTF/JP/Regular.otf',
                 'local_path': 'fonts/subset.otf',
                 'sha256': hashlib.sha256(payload).hexdigest()},
                {'id': 'system', 'source_url': None, 'local_path': 'system.ttc'},
                {'id': 'direct', 'source_url': direct.as_uri(),
                 'local_path': 'fonts/direct.ttf',
                 'sha256': hashlib.sha256(direct.read_bytes()).hexdigest()},
            ]
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'fonts': fonts}))
            with patch.object(fetch_assets, 'ROOT', root), \
                    patch.object(fetch_assets, 'MANIFEST', manifest):
                for force in (False, True):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        self.assertEqual(fetch_assets.fetch_fonts(force), 2)
                    self.assertIn('skip derived (source_url is null', stderr.getvalue())
                    self.assertIn('skip system (source_url is null', stderr.getvalue())
                    self.assertNotIn('mismatch', stderr.getvalue())
                    self.assertEqual((root / 'fonts/subset.otf').read_bytes(), payload)
                    self.assertEqual((root / 'fonts/direct.ttf').read_bytes(), direct.read_bytes())
                # A wrong expected digest must still be reported after extraction.
                fonts[1]['sha256'] = '0' * 64
                manifest.write_text(json.dumps({'fonts': fonts}))
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    fetch_assets.fetch_fonts(force=True)
                self.assertIn('SHA-256 mismatch for subset', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
