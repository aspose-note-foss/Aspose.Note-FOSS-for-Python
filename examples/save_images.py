from pathlib import Path

from aspose.note import Document, Image


out_dir = Path("out_images")
out_dir.mkdir(exist_ok=True)

doc = Document("../testfiles/3ImagesWithDifferentAlignment.one")
for i, img in enumerate(doc.GetChildNodes(Image), start=1):
    name = img.FileName or f"image_{i}.png"
    (out_dir / name).write_bytes(img.Bytes)
