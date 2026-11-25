import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.table_validator import find_large_tables  # noqa: E402

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>t</title></head>
<body>
{body}
</body>
</html>
"""


def table(text, table_id="t1", markup_padding=0):
    pad = " " * markup_padding
    return (
        f'<table id="{table_id}" class="x{pad}"><tbody>'
        f'<tr><td><p class="c">{text}</p></td></tr>'
        "</tbody></table>"
    )


def make_epub(files):
    fd, path = tempfile.mkstemp(suffix=".epub")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, body in files.items():
            z.writestr(name, XHTML.format(body=body))
    return path


class FindLargeTablesTest(unittest.TestCase):
    def tearDown(self):
        for p in getattr(self, "_paths", []):
            os.remove(p)

    def epub(self, files):
        path = make_epub(files)
        self._paths = getattr(self, "_paths", []) + [path]
        return path

    def test_flags_table_with_more_than_limit(self):
        path = self.epub({"OEBPS/cap_026.xhtml": table("a" * 20001, "table001-4")})
        found = find_large_tables(path, max_chars=20000)
        self.assertEqual(len(found), 1)
        item = found[0]
        self.assertEqual(item["file"], "OEBPS/cap_026.xhtml")
        self.assertEqual(item["id"], "table001-4")
        self.assertEqual(item["table"], 1)
        self.assertEqual(item["chars"], 20001)
        self.assertGreater(item["line"], 0)
        self.assertTrue(item["preview"].startswith("aaa"))

    def test_table_exactly_at_limit_passes(self):
        path = self.epub({"OEBPS/c.xhtml": table("a" * 20000)})
        self.assertEqual(find_large_tables(path, max_chars=20000), [])

    def test_markup_is_not_counted(self):
        # lots of markup, little text: must pass
        path = self.epub({"OEBPS/c.xhtml": table("short text", markup_padding=30000)})
        self.assertEqual(find_large_tables(path, max_chars=20000), [])

    def test_whitespace_is_collapsed(self):
        text = "word " + ("\n\t\t   " * 10000) + "word"
        path = self.epub({"OEBPS/c.xhtml": table(text)})
        self.assertEqual(find_large_tables(path, max_chars=20000), [])

    def test_reports_only_large_tables_across_files(self):
        path = self.epub({
            "OEBPS/a.xhtml": table("small", "a1") + table("b" * 25000, "a2"),
            "OEBPS/b.xhtml": table("c" * 30000, "b1"),
            "OEBPS/c.xhtml": table("small", "c1"),
        })
        found = find_large_tables(path, max_chars=20000)
        self.assertEqual(
            [(f["file"], f["table"], f["id"], f["chars"]) for f in found],
            [("OEBPS/a.xhtml", 2, "a2", 25000), ("OEBPS/b.xhtml", 1, "b1", 30000)],
        )

    def test_no_tables_returns_empty(self):
        path = self.epub({"OEBPS/c.xhtml": "<p>no tables</p>"})
        self.assertEqual(find_large_tables(path, max_chars=20000), [])


if __name__ == "__main__":
    unittest.main()
