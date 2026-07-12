# Chart Digitizer Case Study

This section was generated from local PDF files. The PDFs and rendered figure-page PNGs are not committed.

| # | PDF name | Figure page | Figure | Chart type | Multi-subplot | Auto result | Axis result | Curve result | Needs improvement |
| ---: | --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | 024c374dbec7566d9766feebaf395fba.pdf | 4 | rendered page candidate | line_chart | yes | success | auto_geometry_preview | 4 series across 4 subplot(s) | add OCR/manual tick calibration |
| 2 | 019b03a3f5ad34f4b8b9d94ee8f6d020.pdf | 1 | rendered page candidate | line_chart | yes | success | auto_geometry_preview | 3 series across 3 subplot(s) | add OCR/manual tick calibration |
| 3 | 01eadb346d60e0bf640cbbaabbc5708b.pdf | 2 | rendered page candidate | line_chart | no | success | pdf_text | 1 series across 1 subplot(s) | add hand-labeled ground truth for point error |
| 4 | 01f089b279cfc27320a8838ac328331a.pdf | 2 | rendered page candidate | line_chart | no | success | pdf_text | 1 series across 1 subplot(s) | add hand-labeled ground truth for point error |
| 5 | 0059524f440155f52c62d566d20c048d.pdf | 3 | rendered page candidate | line_chart | no | success | pdf_text | 1 series across 1 subplot(s) | add hand-labeled ground truth for point error |
| 6 | 00ecc12918ef92739f5306f36eaceb9c.pdf | 4 | rendered page candidate | line_chart | no | success | pdf_text | 1 series across 1 subplot(s) | add hand-labeled ground truth for point error |
| 7 | 00b79f6f96f2f0d91d08ea45e781e65d.pdf | 4 | rendered page candidate | line_chart | no | success | pdf_text | 1 series across 1 subplot(s) | add hand-labeled ground truth for point error |
| 8 | 0096ebb53022593c7396337e942d3523.pdf | 3 | rendered page candidate | line_chart | no | success | pdf_text | 1 series across 1 subplot(s) | manual review or calibration |
| 9 | 0209cc71ea9131cb6ac62cd7f0e42138.pdf | 2 | rendered page candidate | line_chart | no | success | pdf_text | 4 series across 1 subplot(s) | manual review or calibration |
| 10 | 026bc8059441a145ec16aede13ce85d2.pdf | 3 | rendered page candidate | line_chart | no | success | pdf_text | 6 series across 1 subplot(s) | manual review or calibration |

## JSON Samples

### Case 1: 024c374dbec7566d9766feebaf395fba.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_17",
    "elementId": "pdf_17_page_4_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\024c374dbec7566d9766feebaf395fba.pdf",
    "sourceSha256": "7525976b792d58493fe587e3632c7eb2157341ee7db208e2dde35d2f3ee0ddb3",
    "page": 3,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_17_page_004_clip_01.png",
    "caption": "Fig.3 TGAcurvesofrGO/Scomposites"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:46:22+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.5956146697300333,
    "needsReview": true,
    "status": "需要手动校准",
    "warnings": [
      "未能可靠分离曲线，需要手动选择曲线或颜色。",
      "需要手动校准。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        262.0,
        194.0
      ],
      "plotAreaPx": [
        87.0,
        11.0,
        249.0,
        180.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 0.0,
          "max": 1.0,
          "calibration": [
            {
              "pixel": [
                87.0,
                180.0
              ],
              "value": 0.0
            },
            {
              "pixel": [
                249.0,
                180.0
              ],
              "value": 1.0
            }
          ],
          "source": "auto_geometry_preview",
          "confidence": 0.48
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 0.0,
          "max": 1.0,
          "calibration": [
            {
              "pixel": [
                87.0,
                180.0
              ],
              "value": 0.0
            },
            {
              "pixel": [
                87.0,
                11.0
              ],
              "value": 1.0
            }
          ],
          "source": "auto_geometry_preview",
          "confidence": 0.48
        }
      },
      "legendCandidates": [
        {
          "text": "第49卷 第2期 液相制备石墨烯/硫复合材料及其在锂硫电池正极中的应用",
          "pixel": [
            193.0954885482788,
            29.333749771118164
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "液相制备石墨烯/硫复合材料及其在锂硫电池正极中的应用",
          "pixel": [
            261.3109893798828,
            28.65475082397461
          ],
          "source": "pdf_text",
          "confidence": 0.58
        }
      ],
      "series": [],
      "confidence": 0.39930953929247454,
      "needsReview": true,
      "warnings": [
        "未能可靠分离曲线，需要手动选择曲线或颜色。"
      ]
    }
  ]
}
```

Conclusion: Usable after review/calibration.

### Case 2: 019b03a3f5ad34f4b8b9d94ee8f6d020.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_11",
    "elementId": "pdf_11_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\019b03a3f5ad34f4b8b9d94ee8f6d020.pdf",
    "sourceSha256": "c6d166ea6f82892996ab78e2791a0aaaec224d7644555866d6f1d4726e666a32",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_11_page_001_clip_01.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:45:46+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.6595507248057914,
    "needsReview": true,
    "status": "需要手动校准",
    "warnings": [
      "坐标轴识别置信度低，需要手动校准。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        198.0,
        506.0
      ],
      "plotAreaPx": [
        21.0,
        30.0,
        189.0,
        255.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 0.0,
          "max": 1.0,
          "calibration": [
            {
              "pixel": [
                21.0,
                255.0
              ],
              "value": 0.0
            },
            {
              "pixel": [
                189.0,
                255.0
              ],
              "value": 1.0
            }
          ],
          "source": "auto_geometry_preview",
          "confidence": 0.48
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 0.0,
          "max": 1.0,
          "calibration": [
            {
              "pixel": [
                21.0,
                255.0
              ],
              "value": 0.0
            },
            {
              "pixel": [
                21.0,
                30.0
              ],
              "value": 1.0
            }
          ],
          "source": "auto_geometry_preview",
          "confidence": 0.48
        }
      },
      "legendCandidates": [
        {
          "text": "Author(s) Qi, Qi; Deng, Yaqian; Gu, Sichen et al.",
          "pixel": [
            184.37850379943848,
            97.86272491455078
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "L-Cysteine-Modified",
          "pixel": [
            180.1774444580078,
            52.85137237548828
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Acacia",
          "pixel": [
            240.9427719116211,
            52.85137237548828
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "Gum",
          "pixel": [
            265.6990051269531,
            52.85137237548828
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "Qi,",
          "pixel": [
            144.16836547851562,
            97.86272491455078
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Qi;",
          "pixel": [
            162.17290496826172,
            97.86272491455078
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Deng,",
          "pixel": [
            184.67858123779297,
            97.86272491455078
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "Yaqian;",
          "pixel": [
            216.18653106689453,
            97.86272491455078
          ],
          "source": "pdf_text",
          "confidence": 0.58
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "Author(s) Qi, Qi; Deng, Yaqian; Gu, Sichen et al.",
          "nameSou
```

Conclusion: Usable after review/calibration.

### Case 3: 01eadb346d60e0bf640cbbaabbc5708b.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_14",
    "elementId": "pdf_14_page_2_clip_2",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\01eadb346d60e0bf640cbbaabbc5708b.pdf",
    "sourceSha256": "4f2e0a804ad8cb54de271a1ea4b427e8c6d1e2070a7b357ae3846c3471b8049e",
    "page": 1,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_14_page_002_clip_02.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:46:07+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.7155032565825563,
    "needsReview": false,
    "status": "自动结果",
    "warnings": [
      "坐标轴自动识别置信度较低。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        596.0,
        469.0
      ],
      "plotAreaPx": [
        71.0,
        37.0,
        549.0,
        413.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 1.0,
          "max": 500.0,
          "calibration": [
            {
              "pixel": [
                329.9028625488281,
                474.06318115234376
              ],
              "value": 1.0
            },
            {
              "pixel": [
                539.5592041015625,
                462.1012060546875
              ],
              "value": 500.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 27.0,
          "max": 2025.0,
          "calibration": [
            {
              "pixel": [
                7.9120001792907715,
                55.99903320312498
              ],
              "value": 2025.0
            },
            {
              "pixel": [
                7.9120001792907715,
                97.87903808593748
              ],
              "value": 27.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "mate-",
          "pixel": [
            541.5690002441406,
            7.764597167968731
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "with",
          "pixel": [
            544.087158203125,
            19.726785888671856
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "critical",
          "pixel": [
            539.1719360351562,
            31.68873046874998
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "designing",
          "pixel": [
            322.7226867675781,
            43.650675048828106
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "factors",
          "pixel": [
            358.2516784667969,
            43.650675048828106
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "of",
          "pixel": [
            378.2581787109375,
            43.650675048828106
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "host",
          "pixel": [
            393.4695129394531,
            43.650675048828106
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "materials.50",
          "pixel": [
            427.3426971435547,
            43.34240173339842
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "mate-",
          "nameSource": "
```

Conclusion: Usable after review/calibration.

### Case 4: 01f089b279cfc27320a8838ac328331a.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_15",
    "elementId": "pdf_15_page_2_clip_2",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\01f089b279cfc27320a8838ac328331a.pdf",
    "sourceSha256": "84db14bcce738e957bba031ce3d028ec05030e81747ccbad7ee7bcc8d682c515",
    "page": 1,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_15_page_002_clip_02.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:46:12+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.7151331176345652,
    "needsReview": false,
    "status": "自动结果",
    "warnings": [
      "坐标轴自动识别置信度较低。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        596.0,
        469.0
      ],
      "plotAreaPx": [
        71.0,
        37.0,
        549.0,
        413.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 0.1,
          "max": 150.0,
          "calibration": [
            {
              "pixel": [
                58.24988555908203,
                462.1004736328125
              ],
              "value": 0.1
            },
            {
              "pixel": [
                545.741455078125,
                438.17695068359376
              ],
              "value": 150.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 1.0,
          "max": 27.0,
          "calibration": [
            {
              "pixel": [
                7.9120001792907715,
                17.987039794921856
              ],
              "value": 27.0
            },
            {
              "pixel": [
                77.94573974609375,
                306.64924072265626
              ],
              "value": 1.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "Synthesis of cathode active materials",
          "pixel": [
            377.0199279785156,
            42.006021728515606
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Synthesis",
          "pixel": [
            321.9251403808594,
            42.006021728515606
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "of",
          "pixel": [
            347.2486572265625,
            42.006021728515606
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "cathode",
          "pixel": [
            369.71551513671875,
            42.006021728515606
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "active",
          "pixel": [
            399.56793212890625,
            42.006021728515606
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "materials",
          "pixel": [
            432.2088623046875,
            42.006021728515606
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "powder",
          "pixel": [
            347.67242431640625,
            57.937784423828106
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "was",
          "pixel": [
            372.8802795410156,
            57.937784423828106
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "Synthes
```

Conclusion: Usable after review/calibration.

### Case 5: 0059524f440155f52c62d566d20c048d.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_1",
    "elementId": "pdf_1_page_3_clip_2",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\0059524f440155f52c62d566d20c048d.pdf",
    "sourceSha256": "1007fa7bec0bb7ecacadc21ee520b23715a3046e7419a36762875c8186feb6ed",
    "page": 2,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_01_page_003_clip_02.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:43:17+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.7113572516071809,
    "needsReview": false,
    "status": "自动结果",
    "warnings": [
      "坐标轴自动识别置信度较低。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        596.0,
        469.0
      ],
      "plotAreaPx": [
        71.0,
        37.0,
        549.0,
        413.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 1.7,
          "max": 4.0,
          "calibration": [
            {
              "pixel": [
                42.519012451171875,
                461.83356689453126
              ],
              "value": 1.7
            },
            {
              "pixel": [
                486.8291320800781,
                426.2147314453125
              ],
              "value": 4.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 12.0,
          "max": 2017.0,
          "calibration": [
            {
              "pixel": [
                7.9120001792907715,
                63.66504882812498
              ],
              "value": 2017.0
            },
            {
              "pixel": [
                64.71660804748535,
                288.28071044921876
              ],
              "value": 12.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "Results and discussion",
          "pixel": [
            375.6288299560547,
            141.69823669433592
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "CNT@TiO2 composites and interlayers",
          "pixel": [
            380.3280029296875,
            157.65900634765623
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "spectroscopic",
          "pixel": [
            527.2304077148438,
            16.267618408203106
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "sessions",
          "pixel": [
            536.8997497558594,
            28.22956298828123
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "situ",
          "pixel": [
            331.0447082519531,
            40.191507568359356
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "EDX",
          "pixel": [
            348.64910888671875,
            40.191507568359356
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "on",
          "pixel": [
            364.6068878173828,
            40.191507568359356
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "JEOL",
          "pixel": [
            388.77239990234375,
            40.191507568359356
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "na
```

Conclusion: Usable after review/calibration.

### Case 6: 00ecc12918ef92739f5306f36eaceb9c.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_6",
    "elementId": "pdf_6_page_4_clip_2",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\00ecc12918ef92739f5306f36eaceb9c.pdf",
    "sourceSha256": "0b80b9e04d44cb2762bceb73b715f29ac41b8f1524b2a295d4c18792051ea140",
    "page": 3,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_06_page_004_clip_02.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:45:26+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.6960707247645747,
    "needsReview": false,
    "status": "自动结果",
    "warnings": [
      "坐标轴自动识别置信度较低。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        596.0,
        470.0
      ],
      "plotAreaPx": [
        71.0,
        37.0,
        549.0,
        414.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 1.0,
          "max": 3.0,
          "calibration": [
            {
              "pixel": [
                50.0792179107666,
                443.16466796875
              ],
              "value": 1.0
            },
            {
              "pixel": [
                152.3662567138672,
                469.13091552734375
              ],
              "value": 3.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 1.0,
          "max": 2.0,
          "calibration": [
            {
              "pixel": [
                49.45817756652832,
                156.72001159667968
              ],
              "value": 2.0
            },
            {
              "pixel": [
                50.0792179107666,
                443.16466796875
              ],
              "value": 1.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "2.1 | One‐dimensional nanocarbon",
          "pixel": [
            412.9622039794922,
            117.37884033203125
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Review",
          "pixel": [
            534.9929809570312,
            14.171564941406245
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "carbon‐",
          "pixel": [
            534.3235473632812,
            26.906016235351558
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "based",
          "pixel": [
            319.73187255859375,
            40.137812499999995
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "flexible",
          "pixel": [
            352.9881896972656,
            40.137812499999995
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "self‐supporting",
          "pixel": [
            406.01475524902344,
            39.88914001464843
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "cathodes",
          "pixel": [
            462.2763366699219,
            40.137812499999995
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "provide",
          "pixel": [
            502.770751953125,
            40.137812499999995
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "Review",
     
```

Conclusion: Usable after review/calibration.

### Case 7: 00b79f6f96f2f0d91d08ea45e781e65d.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_3",
    "elementId": "pdf_3_page_4_clip_2",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\00b79f6f96f2f0d91d08ea45e781e65d.pdf",
    "sourceSha256": "862b2f5c585a4af94e94d0b6ffc71a58124195c777164cf1886f06caf944afb8",
    "page": 3,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_03_page_004_clip_02.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:43:29+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.6923039826775105,
    "needsReview": false,
    "status": "自动结果",
    "warnings": [
      "坐标轴自动识别置信度较低。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        596.0,
        417.0
      ],
      "plotAreaPx": [
        71.0,
        33.0,
        549.0,
        367.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 827.0,
          "max": 2019.0,
          "calibration": [
            {
              "pixel": [
                132.82095336914062,
                361.10149047851564
              ],
              "value": 2019.0
            },
            {
              "pixel": [
                544.6307373046875,
                397.46675537109377
              ],
              "value": 827.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 2.0,
          "max": 2016.0,
          "calibration": [
            {
              "pixel": [
                80.34650802612305,
                34.667728881835956
              ],
              "value": 2.0
            },
            {
              "pixel": [
                79.59489822387695,
                279.90361450195314
              ],
              "value": 2016.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "(Lin",
          "pixel": [
            323.0465850830078,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "et",
          "pixel": [
            333.060302734375,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "al.,",
          "pixel": [
            342.23158264160156,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Copyright",
          "pixel": [
            388.23480224609375,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Springer",
          "pixel": [
            434.8761901855469,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Nature.",
          "pixel": [
            460.4601135253906,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Composite",
          "pixel": [
            500.7653503417969,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "Li",
          "pixel": [
            521.6280212402344,
            34.667728881835956
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "(Lin",
          "nameSource": "p
```

Conclusion: Usable after review/calibration.

### Case 8: 0096ebb53022593c7396337e942d3523.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_2",
    "elementId": "pdf_2_page_3_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\0096ebb53022593c7396337e942d3523.pdf",
    "sourceSha256": "1bd2a95dbe45e0b28ab48562e92befe8801e6dc86f3f32af8e9dcebc52ac89a4",
    "page": 2,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_02_page_003_clip_01.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:43:21+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.6841492128797904,
    "needsReview": true,
    "status": "需要手动校准",
    "warnings": [
      "坐标轴自动识别置信度较低。",
      "需要手动校准。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        596.0,
        408.0
      ],
      "plotAreaPx": [
        58.0,
        24.0,
        567.0,
        236.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 1.0,
          "max": 3.0,
          "calibration": [
            {
              "pixel": [
                87.32140731811523,
                250.30808593750004
              ],
              "value": 3.0
            },
            {
              "pixel": [
                102.11268615722656,
                267.9657397460938
              ],
              "value": 1.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 2.0,
          "max": 3.0,
          "calibration": [
            {
              "pixel": [
                86.51608657836914,
                90.44389678955082
              ],
              "value": 2.0
            },
            {
              "pixel": [
                87.32140731811523,
                250.30808593750004
              ],
              "value": 3.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "performed",
          "pixel": [
            343.34222412109375,
            34.52107955932621
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "in",
          "pixel": [
            371.33668518066406,
            34.52107955932621
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "an",
          "pixel": [
            383.7748107910156,
            34.52107955932621
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "electrolyte",
          "pixel": [
            412.0428466796875,
            34.52107955932621
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "containing",
          "pixel": [
            456.11712646484375,
            34.52107955932621
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "molar",
          "pixel": [
            506.98475646972656,
            34.52107955932621
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "lithium",
          "pixel": [
            536.3388366699219,
            34.52107955932621
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "perchlorate",
          "pixel": [
            326.6953887939453,
            45.97804977416996
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "performed",
          "nam
```

Conclusion: Usable after review/calibration.

### Case 9: 0209cc71ea9131cb6ac62cd7f0e42138.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_16",
    "elementId": "pdf_16_page_2_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\0209cc71ea9131cb6ac62cd7f0e42138.pdf",
    "sourceSha256": "6230d6a43e20b24a1a7ad03499c1daf7407d46e85d9745eb98e7fbcd0d237c2a",
    "page": 1,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_16_page_002_clip_01.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:46:17+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.6447389287933006,
    "needsReview": true,
    "status": "需要手动校准",
    "warnings": [
      "坐标轴自动识别置信度较低。",
      "需要手动校准。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        440.0,
        400.0
      ],
      "plotAreaPx": [
        52.0,
        32.0,
        405.0,
        352.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 2015.0,
          "max": 2016.0,
          "calibration": [
            {
              "pixel": [
                57.31607627868652,
                344.76042602539064
              ],
              "value": 2015.0
            },
            {
              "pixel": [
                291.12860107421875,
                344.76042602539064
              ],
              "value": 2016.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 1.0,
          "max": 2015.0,
          "calibration": [
            {
              "pixel": [
                49.79628372192383,
                9.539537887573239
              ],
              "value": 1.0
            },
            {
              "pixel": [
                57.31607627868652,
                344.76042602539064
              ],
              "value": 2015.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "exclusively,",
          "pixel": [
            254.66912078857422,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "as",
          "pixel": [
            282.47845458984375,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "in",
          "pixel": [
            292.0391082763672,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "the",
          "pixel": [
            303.3464660644531,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "case",
          "pixel": [
            318.93177795410156,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "of",
          "pixel": [
            332.7084045410156,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "battery",
          "pixel": [
            351.2826843261719,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "electric",
          "pixel": [
            379.30262756347656,
            33.96818206787109
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "exclusively,",
       
```

Conclusion: Usable after review/calibration.

### Case 10: 026bc8059441a145ec16aede13ce85d2.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_19",
    "elementId": "pdf_19_page_3_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\026bc8059441a145ec16aede13ce85d2.pdf",
    "sourceSha256": "508247db0c4bc3fd5479516ef3699895797cad4d1dfcabfaec3f32190b748aa3",
    "page": 2,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_19_page_003_clip_01.png",
    "caption": "Fig. line curve voltage current capacity time spectrum"
  },
  "analysis": {
    "chartType": "line_chart",
    "createdAt": "2026-07-02T00:46:32+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.584284333002343,
    "needsReview": true,
    "status": "需要手动校准",
    "warnings": [
      "坐标轴自动识别置信度较低。",
      "需要手动校准。"
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "label": "a",
      "bboxPx": [
        0.0,
        0.0,
        596.0,
        510.0
      ],
      "plotAreaPx": [
        71.0,
        40.0,
        549.0,
        449.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 1.0,
          "max": 943.1,
          "calibration": [
            {
              "pixel": [
                60.01534652709961,
                467.45749633789063
              ],
              "value": 943.1
            },
            {
              "pixel": [
                340.35235595703125,
                463.6364208984375
              ],
              "value": 1.0
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 2.45,
          "max": 943.1,
          "calibration": [
            {
              "pixel": [
                57.770870208740234,
                141.29749267578126
              ],
              "value": 2.45
            },
            {
              "pixel": [
                60.01534652709961,
                467.45749633789063
              ],
              "value": 943.1
            }
          ],
          "source": "pdf_text",
          "confidence": 0.78
        }
      },
      "legendCandidates": [
        {
          "text": "sharp",
          "pixel": [
            538.1383361816406,
            17.457496337890632
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "mV",
          "pixel": [
            542.3934020996094,
            28.737498931884772
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "resting",
          "pixel": [
            338.2651672363281,
            40.01749389648438
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "for",
          "pixel": [
            359.4818878173828,
            40.01749389648438
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "week",
          "pixel": [
            386.0653381347656,
            40.01749389648438
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "(Figure",
          "pixel": [
            412.9599151611328,
            40.01749389648438
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "The",
          "pixel": [
            455.3882293701172,
            40.01749389648438
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "much",
          "pixel": [
            476.6023864746094,
            40.01749389648438
          ],
          "source": "pdf_text",
          "confidence": 0.5
        }
      ],
      "series": [
        {
          "seriesId": "series_1",
          "name": "sharp",
          "nameSource": "pd
```

Conclusion: Usable after review/calibration.
