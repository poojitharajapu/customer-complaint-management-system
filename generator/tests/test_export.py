"""Temporary-directory checks for deterministic CSV, JSON, and executable SQL exports."""

import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from generator.export import dataset_tables, export_complete_dataset
from generator.phase8 import generate_complete_dataset


class ExportTests(unittest.TestCase):
    def test_csv_json_sql_and_checksums_are_complete_and_reproducible(self):
        dataset = generate_complete_dataset("starter")
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            sums1 = export_complete_dataset(dataset, first)
            sums2 = export_complete_dataset(generate_complete_dataset("starter"), second)
            self.assertEqual(sums1, sums2)
            for name, expected_rows in dataset_tables(dataset).items():
                json_rows = json.loads((Path(first) / f"{name}.json").read_text(encoding="utf-8"))
                with (Path(first) / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
                    csv_rows = list(csv.DictReader(handle))
                self.assertEqual(len(json_rows), len(expected_rows), name)
                self.assertEqual(len(csv_rows), len(expected_rows), name)
                for json_row, csv_row in zip(json_rows, csv_rows):
                    for key, value in json_row.items():
                        if isinstance(value, (dict, list)):
                            expected_csv = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        elif value is None:
                            expected_csv = ""
                        elif isinstance(value, bool):
                            expected_csv = "true" if value else "false"
                        else:
                            expected_csv = str(value)
                        self.assertEqual(csv_row[key], expected_csv, f"{name}.{key}")
            self.assertNotIn("expected_category", dataset_tables(dataset)["complaints"][0])
            self.assertNotIn("severity", dataset_tables(dataset)["complaints"][0])
            self.assertIn("expected_category", dataset_tables(dataset)["ground_truth"][0])
            sql_path = Path(first) / "seed.sql"
            connection = sqlite3.connect(":memory:")
            connection.executescript(sql_path.read_text(encoding="utf-8"))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0], 20)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            connection.close()
            checksum_manifest = json.loads((Path(first) / "checksums.sha256.json").read_text(encoding="utf-8"))
            for filename, checksum in checksum_manifest.items():
                self.assertEqual(hashlib.sha256((Path(first) / filename).read_bytes()).hexdigest(), checksum)


if __name__ == "__main__": unittest.main()
