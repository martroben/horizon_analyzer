# standard
import html.parser
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile


##########
# Inputs #
##########

# Elements that start a new line in the text
XML_BLOCK_TAGS = {
    # JATS (PMC)
    "article-title", "abstract", "sec", "title", "p", "caption", "label", "fig", "table-wrap", "tr", "list-item",
    "fn", "notes", "ack", "back", "body", "ref", "supplementary-material", "data-availability", "funding-group",
    "award-group", "funding-statement", "disp-quote", "boxed-text",
    # TEI (GROBID)
    "head", "div", "figure", "note", "biblStruct", "row", "item", "titleStmt", "listBibl"
}
XML_SKIP_TAGS = {
    "contrib-group", "aff", "author-notes", "pub-date", "history", "permissions", "kwd-group", "counts", "custom-meta-group",
    "journal-meta", "article-categories", "article-id", "article-version", "pub-history", "volume", "issue", "fpage",
    "lpage", "elocation-id", "processing-meta", "issn", "publisher", "graphic", "inline-graphic", "tex-math",
    "mml:math", "{http://www.w3.org/1998/Math/MathML}math"
}
XML_TITLE_TAGS = {"article-title", "title", "head"}
XML_LINK_ATTRIBUTES = ["{http://www.w3.org/1999/xlink}href", "target", "href"]

HTML_BLOCK_TAGS = {
    "p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br", "table", "figcaption",
    "caption", "dd", "dt", "blockquote", "pre"
}
HTML_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button", "select", "template", "iframe"}
HTML_TITLE_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WORD_RELATIONSHIP_ID_ATTRIBUTE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
WORD_SKIP_TAGS = {"pPr", "rPr", "sectPr", "delText", "footnotePr", "endnotePr"}
    # Paragraph and run properties (incl. tab stop definitions), section properties, deleted text of tracked changes
WORD_PARTS = [("document", None), ("footnotes", "Footnotes"), ("endnotes", "Endnotes")]
    # Parts of a .docx file with text, with the heading that the part gets in the text


#########################
# Classes and functions #
#########################

def strip_namespace(tag: str) -> str:
    """
    Gives the XML tag without namespace, e.g. {http://www.tei-c.org/ns/1.0}div -> div.
    """
    return tag.rsplit("}", 1)[-1]


def get_link_target(element: ET.Element) -> str | None:
    """
    Gives the link target of an XML element (xlink:href in JATS, target in TEI) if it has one.
    """
    for attribute in XML_LINK_ATTRIBUTES:
        if element.get(attribute):
            return element.get(attribute).strip()
    return None


def xml_to_text(xml_string: str) -> str:
    """
    Converts JATS XML (PMC) or TEI XML (GROBID) to plain text.
    Section titles are marked with #. Link targets that are not in the link text are added in brackets.
    """
    root = ET.fromstring(xml_string)
    parts = []

    def walk(element: ET.Element) -> None:
        tag = element.tag if isinstance(element.tag, str) else ""
        if tag in XML_SKIP_TAGS or strip_namespace(tag) in XML_SKIP_TAGS:
            if element.tail:
                parts.append(element.tail)
            return
        short_tag = strip_namespace(tag)
        is_block = short_tag in XML_BLOCK_TAGS
        if is_block:
            parts.append("\n")
        if short_tag in XML_TITLE_TAGS:
            parts.append("# ")
        start = len(parts)
        if element.text:
            parts.append(element.text)
        for child in element:
            walk(child)
        # Keep link targets, e.g. repository URLs behind "here" or supplementary file names
        link_target = get_link_target(element)
        if link_target and short_tag not in {"graphic", "inline-graphic"}:
            link_text = "".join(parts[start:])
            if link_target not in link_text:
                parts.append(f' [{link_target}]')
        if is_block:
            parts.append("\n")
        if element.tail:
            parts.append(element.tail)

    walk(root)
    return tidy_text("".join(parts))


class HtmlTextParser(html.parser.HTMLParser):
    """
    Collects the visible text of an HTML page.
    Links to other sites are added in brackets, because data availability statements often link to repositories.
    """
    def __init__(self, page_URL: str = None) -> None:
        super().__init__(convert_charrefs=True)
        self.page_host = urllib.parse.urlparse(page_URL).netloc if page_URL else ""
        self.parts = []
        self.skip_depth = 0
        self.open_links = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in HTML_SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in HTML_BLOCK_TAGS:
            self.parts.append("\n")
        if tag in HTML_TITLE_TAGS:
            self.parts.append("# ")
        if tag == "a":
            href = dict(attrs).get("href") or ""
            self.open_links.append((href, len(self.parts)))

    def handle_endtag(self, tag: str) -> None:
        if tag in HTML_SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == "a" and self.open_links:
            href, start = self.open_links.pop()
            host = urllib.parse.urlparse(href).netloc
            link_text = "".join(self.parts[start:])
            if href.startswith("http") and host and host != self.page_host and href not in link_text:
                self.parts.append(f' [{href}]')
        if tag in HTML_BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html_string: str, page_URL: str = None) -> str:
    """
    Converts an HTML page to plain text. Headings are marked with #.
    """
    parser = HtmlTextParser(page_URL)
    parser.feed(html_string)
    parser.close()
    return tidy_text("".join(parser.parts))


def word_xml_to_text(xml_string: bytes, relationships: dict) -> str:
    """
    Converts a WordprocessingML part of a .docx file (document, footnotes, endnotes) to plain text.
    Paragraphs with a heading or title style are marked with #. Link targets that are not in the link text are added in brackets.
    relationships: relationship IDs and targets of the part's external links.
    """
    root = ET.fromstring(xml_string)
    parts = []
    field_links = []

    def walk(element: ET.Element) -> None:
        tag = strip_namespace(element.tag)
        if tag in WORD_SKIP_TAGS:
            return
        if tag == "instrText":
            # Field codes are not visible text (e.g. Zotero citations), but HYPERLINK fields have link targets
            match = re.search(r'HYPERLINK\s+"([^"]+)"', element.text or "")
            if match:
                field_links.append(match.group(1))
            return
        if tag == "p":
            parts.append("\n")
            style = element.find(f'{WORD_NAMESPACE}pPr/{WORD_NAMESPACE}pStyle')
            if style is not None and re.match(r"heading|title", style.get(f'{WORD_NAMESPACE}val', ""), flags=re.IGNORECASE):
                parts.append("# ")
        elif tag == "t":
            parts.append(element.text or "")
        elif tag == "tab":
            parts.append("\t")
        elif tag in ("br", "cr"):
            parts.append("\n")
        start = len(parts)
        for child in element:
            walk(child)
        if tag == "hyperlink":
            link_target = relationships.get(element.get(WORD_RELATIONSHIP_ID_ATTRIBUTE))
            if link_target and link_target not in "".join(parts[start:]):
                parts.append(f' [{link_target}]')
        if tag == "p":
            paragraph_text = "".join(parts[start:])
            parts.extend(f' [{link}]' for link in field_links if link not in paragraph_text)
            field_links.clear()
            parts.append("\n")

    walk(root)
    return "".join(parts)


def docx_to_text(docx_path: str) -> str:
    """
    Converts a Word document (.docx) to plain text: the body, then footnotes and endnotes.
    """
    texts = []
    with zipfile.ZipFile(docx_path) as docx_file:
        names = docx_file.namelist()
        for part, heading in WORD_PARTS:
            if f'word/{part}.xml' not in names:
                continue
            relationships = {}
            if f'word/_rels/{part}.xml.rels' in names:
                for relationship in ET.fromstring(docx_file.read(f'word/_rels/{part}.xml.rels')):
                    if relationship.get("TargetMode") == "External":
                        relationships[relationship.get("Id")] = relationship.get("Target")
            text = word_xml_to_text(docx_file.read(f'word/{part}.xml'), relationships)
            if text.strip():
                texts += [f'# {heading}\n{text}' if heading else text]
    return tidy_text("\n".join(texts))


def pdf_to_text(pdf_path: str) -> str:
    """
    Converts a PDF to plain text with pdftotext (poppler-utils).
    """
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext not found. Install poppler-utils (e.g. sudo apt install poppler-utils)")
    result = subprocess.run(["pdftotext", "-q", "-enc", "UTF-8", pdf_path, "-"], capture_output=True, timeout=300)
    return tidy_text(result.stdout.decode("utf8", errors="replace"))


def tidy_text(text: str) -> str:
    """
    Collapses runs of spaces and blank lines.
    """
    text = text.replace("\xa0", " ").replace("\r", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    # Drop heading marks without a heading and keep at most one blank line
    text = re.sub(r"^# *$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def convert_file(path: str, page_URL: str = None) -> str:
    """
    Converts a cached full text file (.pdf, .docx, .xml, .html) to plain text.
    Saves the text next to the original with a .txt extension and gives the text file path.
    """
    stem, extension = os.path.splitext(path)
    extension = extension.lower()
    if extension == ".pdf":
        text = pdf_to_text(path)
    elif extension == ".docx":
        text = docx_to_text(path)
    else:
        with open(path, encoding="utf8", errors="replace") as read_file:
            content = read_file.read()
        if extension == ".xml":
            text = xml_to_text(content)
        elif extension in (".html", ".htm"):
            text = html_to_text(content, page_URL)
        else:
            raise ValueError(f'Unknown full text file type: {path}')

    text_path = f'{stem}.txt'
    with open(text_path, "w", encoding="utf8") as write_file:
        write_file.write(text)
    return text_path


########
# Main #
########

# Usage: uv run src/fulltext_conversion.py <file> [<file> ...]
# Converts full text files that were saved by hand (e.g. a publisher page saved with curl during a check)
if __name__ == "__main__":
    for file_path in sys.argv[1:]:
        text_file_path = convert_file(file_path)
        with open(text_file_path, encoding="utf8") as read_file:
            n_characters = len(read_file.read())
        print(f'{file_path} -> {text_file_path} ({n_characters} characters)')
