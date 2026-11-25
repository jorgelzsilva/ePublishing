import re
import zipfile

from lxml import etree

from config import Config

CONTENT_EXTENSIONS = (".xhtml", ".html", ".htm")
_PARSER = etree.XMLParser(recover=True, huge_tree=True)


def _table_text(table):
    """Visible text of the table, with whitespace collapsed (markup is not counted)."""
    return re.sub(r"\s+", " ", "".join(table.itertext())).strip()


def _parse(data):
    return etree.fromstring(data, parser=_PARSER)


def find_large_tables(epub_path, max_chars=Config.MAX_TABLE_CHARS):
    """
    Lists tables whose text exceeds max_chars characters.
    Kindle (KDP) rejects tables with more than 20,000 characters:
    "Tables with more than 20,000 characters are not currently supported."
    """
    found = []
    with zipfile.ZipFile(epub_path, "r") as z:
        for name in sorted(n for n in z.namelist() if n.lower().endswith(CONTENT_EXTENSIONS)):
            root = _parse(z.read(name))
            if root is None:
                continue
            tables = root.xpath("//*[local-name()='table']")
            for index, tbl in enumerate(tables, 1):
                text = _table_text(tbl)
                chars = len(text)
                if chars > max_chars:
                    found.append({
                        "file": name,
                        "table": index,
                        "id": tbl.get("id", ""),
                        "line": tbl.sourceline or 0,
                        "chars": chars,
                        "preview": text[:80],
                    })
    return found
