"""Launch-validation folders seeded from the cached library.

SCAN_DIRS holds (folder, system) pairs whose folder is a top-level SD
directory -- the shape gamelib.discover_dirs returns -- because launch
paths are validated with path.startswith(f"{folder}/").

Seeding it from each game's "folder" tag instead produced bare letters
on a library organised into A/B/C subfolders: nothing matched
"Genesis/S/...", and every launch from the web UI was rejected as "bad
path" until a rescan happened to replace the seed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

DAEMON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DAEMON_DIR))

from achievementbox.gamelib import scan_dirs_from_library  # noqa: E402


class ScanDirsFromLibraryTest(unittest.TestCase):
    def test_letter_subfolders_yield_their_top_level_directory(self):
        library = [
            {"path": "Genesis/S/Streets of Rage 3 (USA).md",
             "folder": "S", "system": "md"},
            {"path": "Genesis/V/Vectorman (USA, Europe).md",
             "folder": "V", "system": "md"},
        ]
        self.assertEqual(scan_dirs_from_library(library), [("Genesis", "md")])

    def test_every_seeded_folder_validates_its_own_games(self):
        """The property that matters: a launch path must match a seeded
        prefix, which is how api_launch admits it."""
        library = [
            {"path": "Genesis/#/16t (Japan).md", "folder": "#", "system": "md"},
            {"path": "Genesis/S/Streets of Rage 3 (USA).md",
             "folder": "S", "system": "md"},
            {"path": "Mega-CD/Snatcher (Europe)/Snatcher.cue",
             "folder": "Mega-CD", "system": "mcd"},
        ]
        dirs = scan_dirs_from_library(library)
        for game in library:
            match = next((s for d, s in dirs
                          if game["path"].startswith(f"{d}/")), None)
            self.assertEqual(match, game["system"], game["path"])

    def test_flat_library_still_works(self):
        library = [{"path": "MEGA DRIVE/Sonic.md",
                    "folder": "MEGA DRIVE", "system": "md"}]
        self.assertEqual(scan_dirs_from_library(library),
                         [("MEGA DRIVE", "md")])

    def test_results_are_sorted_and_deduplicated(self):
        """discover_dirs returns sorted pairs; the seed matches so the two
        sources cannot disagree on ordering."""
        library = [
            {"path": "Mega-CD/a.cue", "folder": "Mega-CD", "system": "mcd"},
            {"path": "Genesis/A/b.md", "folder": "A", "system": "md"},
            {"path": "Genesis/B/c.md", "folder": "B", "system": "md"},
        ]
        self.assertEqual(scan_dirs_from_library(library),
                         [("Genesis", "md"), ("Mega-CD", "mcd")])

    def test_entries_without_a_usable_path_are_skipped(self):
        library = [{"folder": "S", "system": "md"},
                   {"path": "", "system": "md"},
                   {"path": "Genesis/S/ok.md", "system": "md"}]
        self.assertEqual(scan_dirs_from_library(library), [("Genesis", "md")])


if __name__ == "__main__":
    unittest.main()
