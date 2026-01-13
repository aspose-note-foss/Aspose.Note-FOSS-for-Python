import sys

from aspose.note import Document, RichText


# Windows console may use a legacy encoding (e.g. cp1251) and crash on some characters.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


doc = Document("../testfiles/FormattedRichText.one")
for rt in doc.GetChildNodes(RichText):
    if rt.Text:
        print(rt.Text)
