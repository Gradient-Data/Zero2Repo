# feature: F19

The tests supply real external tools missing from the case image; no network
or package installation is used during acceptance runs.

- F19_debs/: the official Ubuntu noble packages of Graphviz 2.42.2
  (graphviz 2.42.2-9ubuntu0.1) and Tesseract 5.3.4 (tesseract-ocr
  5.3.4-1build5, tesseract-ocr-eng 1:4.1.0-2), plus every package they depend
  on that the case image lacks. They are fetched from Launchpad as listed in
  test_assets.json and unpacked with dpkg-deb into a temporary directory; each
  package carries its upstream copyright notice under usr/share/doc.

The graph renderer processes the supplied DOT input. Tesseract is an independent
observer of rendered pixels, including when the product embeds raster diagrams.
The OCR preprocessing removes long ruling strokes; arrow/edge measurements use
the original pixels. Failure to launch or consume either tool fails the test.
