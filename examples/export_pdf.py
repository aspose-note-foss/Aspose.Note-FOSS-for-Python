from aspose.note import Document, SaveFormat


doc = Document("../testfiles/SimpleTable.one")
doc.Save("out.pdf", SaveFormat.Pdf)