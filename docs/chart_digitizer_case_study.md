# Chart Digitizer Case Study

This section was generated from local PDF files. The PDFs and rendered figure-page PNGs are not committed.

| # | PDF name | Figure page | Figure | Chart type | Multi-subplot | Auto result | Axis result | Curve result | Needs improvement |
| ---: | --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | 000520fbe7cd0e8a53b81bd6e222fe5b.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |
| 2 | 0059524f440155f52c62d566d20c048d.pdf | 4 | rendered page candidate | line_chart | yes | success | rapidocr | 12 series across 2 subplot(s) | add hand-labeled ground truth for point error |
| 3 | 0096ebb53022593c7396337e942d3523.pdf | 5 | rendered page candidate | line_chart | yes | success | auto_geometry_preview, rapidocr, shared_subplot_axis | 5 series across 4 subplot(s) | add OCR/manual tick calibration |
| 4 | 00a24ace7ad86c1c395be83b644d0c91.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |
| 5 | 00b79f6f96f2f0d91d08ea45e781e65d.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |
| 6 | 00bf712842ac0835e17fed73971157eb.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |
| 7 | 00c08eb420b9f04a1e5dc4e0e424ade8.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |
| 8 | 00ecc12918ef92739f5306f36eaceb9c.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |
| 9 | 013b1b5f984c80792444bf226d3f2163.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |
| 10 | 0168023ef6758a93aad74910f554ab0e.pdf | 1 | rendered page candidate | unsupported | no | needs review | not detected | 0 series across 0 subplot(s) | add OCR/manual tick calibration |

## JSON Samples

### Case 1: 000520fbe7cd0e8a53b81bd6e222fe5b.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_1",
    "elementId": "pdf_1_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\000520fbe7cd0e8a53b81bd6e222fe5b.pdf",
    "sourceSha256": "9ba6387366fe60d13a52a14ce9ec8fee9135aef43d89f0dd54e0e666571c82bd",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_01_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:06:33+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.

### Case 2: 0059524f440155f52c62d566d20c048d.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_2",
    "elementId": "pdf_2_page_4_clip_2",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\0059524f440155f52c62d566d20c048d.pdf",
    "sourceSha256": "1007fa7bec0bb7ecacadc21ee520b23715a3046e7419a36762875c8186feb6ed",
    "page": 3,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_02_page_004_clip_02.png",
    "caption": "Fig. 2"
  },
  "analysis": {
    "chartType": "line_chart",
    "eligible": true,
    "createdAt": "2026-07-12T21:06:51+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.8256249593434832,
    "needsReview": false,
    "status": "自动结果",
    "warnings": [],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "passed",
        "confidence": 0.6715755076932347
      },
      {
        "stage": "subplot_split",
        "status": "automatic",
        "count": 2
      },
      {
        "stage": "axis_calibration",
        "status": "passed"
      },
      {
        "stage": "curve_sampling",
        "status": "passed"
      },
      {
        "stage": "data_export",
        "status": "ready"
      }
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "coordinateSystemId": "axes_1",
      "label": "a",
      "bboxPx": [
        86.0,
        56.0,
        311.0,
        288.0
      ],
      "plotAreaPx": [
        117.0,
        69.0,
        300.0,
        248.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 0.0,
          "max": 0.5,
          "calibration": [
            {
              "pixel": [
                207.0,
                248.0
              ],
              "value": 0.0
            },
            {
              "pixel": [
                232.5,
                248.0
              ],
              "value": 0.5
            }
          ],
          "source": "rapidocr",
          "confidence": 0.8160000000000001
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": -0.0002999966507322716,
          "max": 5.056206802058277e-05,
          "calibration": [
            {
              "pixel": [
                117.0,
                92.0
              ],
              "value": 5.056206802058277e-05
            },
            {
              "pixel": [
                117.0,
                247.0
              ],
              "value": -0.0002999966507322716
            }
          ],
          "source": "rapidocr",
          "confidence": 0.8799965550389081
        }
      },
      "legendCandidates": [
        {
          "text": "suggests",
          "pixel": [
            264.3563690185547,
            140.26542480468748
          ],
          "source": "pdf_text",
          "confidence": 0.5
        },
        {
          "text": "that",
          "pixel": [
            308.0079116821289,
            140.26542480468748
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "the",
          "pixel": [
            336.1562805175781,
            140.26542480468748
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "for",
          "pixel": [
            306.097412109375,
            158.20875366210936
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "TiO2",
          "pixel": [
            332.7842445373535,
            158.84574325561522
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "prepared",
          "pixel": [
            377.5536918640137,
            158.20875366210936
          ],
          "source": "pdf_text",
          "confidence": 0.58
        },
        {
          "text": "formed",
          "pixel": [
            323.510398864
```

Conclusion: Usable after review/calibration.

### Case 3: 0096ebb53022593c7396337e942d3523.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_3",
    "elementId": "pdf_3_page_5_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\0096ebb53022593c7396337e942d3523.pdf",
    "sourceSha256": "1bd2a95dbe45e0b28ab48562e92befe8801e6dc86f3f32af8e9dcebc52ac89a4",
    "page": 4,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_03_page_005_clip_01.png",
    "caption": "FIGURE 6 | (A,B) Charge-discharge cycles upto 40 cycles, (C) percentage retention of capacity vs. cycle number, and (D) percentage coulumbic efﬁciency vs. cycle"
  },
  "analysis": {
    "chartType": "line_chart",
    "eligible": true,
    "createdAt": "2026-07-12T21:07:01+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.85093832881879,
    "needsReview": true,
    "status": "需要手动校准",
    "warnings": [
      "需要手动校准。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "passed",
        "confidence": 0.5969706663626847
      },
      {
        "stage": "subplot_split",
        "status": "automatic",
        "count": 4
      },
      {
        "stage": "axis_calibration",
        "status": "review"
      },
      {
        "stage": "curve_sampling",
        "status": "review"
      },
      {
        "stage": "data_export",
        "status": "ready"
      }
    ]
  },
  "subplots": [
    {
      "subplotId": "subplot_1",
      "coordinateSystemId": "axes_1",
      "label": "a",
      "bboxPx": [
        90.0,
        0.0,
        468.0,
        273.0
      ],
      "plotAreaPx": [
        185.0,
        16.0,
        450.0,
        262.0
      ],
      "axes": {
        "x": {
          "label": "",
          "scale": "linear",
          "min": 10.048746235223803,
          "max": 45.0138404489296,
          "calibration": [
            {
              "pixel": [
                232.5,
                479.0
              ],
              "value": 10.048746235223803
            },
            {
              "pixel": [
                442.0,
                479.0
              ],
              "value": 45.0138404489296
            }
          ],
          "source": "shared_subplot_axis",
          "confidence": 0.8447993314802026
        },
        "y": {
          "label": "",
          "scale": "linear",
          "min": 0.0,
          "max": 1.0,
          "calibration": [
            {
              "pixel": [
                185.0,
                262.0
              ],
              "value": 0.0
            },
            {
              "pixel": [
                185.0,
                16.0
              ],
              "value": 1.0
            }
          ],
          "source": "auto_geometry_preview",
          "confidence": 0.48
        }
      },
      "legendCandidates": [],
      "series": [
        {
          "seriesId": "series_1",
          "coordinateSystemId": "axes_1",
          "name": "Series 1",
          "nameSource": "default",
          "color": "#5d5d5d",
          "confidence": 0.9356962025316456,
          "needsReview": false,
          "warnings": [],
          "seedPixel": [],
          "legendCandidate": {},
          "domainCoverage": 0.8943396226415095,
          "markerSeries": false,
          "points": [
            {
              "index": 0,
              "x": 2.1210995757917015,
              "y": 0.25203252032520324,
              "pixel": [
                185.0,
                200.0
              ],
              "confidence": 0.88,
              "missing": false
            },
            {
              "index": 1,
              "x": 6.553164023988828,
              "y": 0.6971544715447154,
              "pixel": [
                211.55555555555554,
                90.5
              ],
              "confidence": 0.88,
              "missing": false
            },
            {
              "index": 2,
              "x": 10.985228472185957,
              "y": 0
```

Conclusion: Usable after review/calibration.

### Case 4: 00a24ace7ad86c1c395be83b644d0c91.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_4",
    "elementId": "pdf_4_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\00a24ace7ad86c1c395be83b644d0c91.pdf",
    "sourceSha256": "a1fcb1229b2d843de6bea0481d6c182e1f2156d08de0d678541999d61c3f00a2",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_04_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:07:06+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.

### Case 5: 00b79f6f96f2f0d91d08ea45e781e65d.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_5",
    "elementId": "pdf_5_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\00b79f6f96f2f0d91d08ea45e781e65d.pdf",
    "sourceSha256": "862b2f5c585a4af94e94d0b6ffc71a58124195c777164cf1886f06caf944afb8",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_05_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:07:39+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.

### Case 6: 00bf712842ac0835e17fed73971157eb.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_6",
    "elementId": "pdf_6_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\00bf712842ac0835e17fed73971157eb.pdf",
    "sourceSha256": "baaf47392f21cdc5ea411af6a53a50942c55861c78155f1ce908ff7f1f4e29d0",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_06_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:07:42+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.

### Case 7: 00c08eb420b9f04a1e5dc4e0e424ade8.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_7",
    "elementId": "pdf_7_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\00c08eb420b9f04a1e5dc4e0e424ade8.pdf",
    "sourceSha256": "07405990995f080b22ba23cd4584998246a23d88214c820a78d8cdbcd7e872f4",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_07_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:08:14+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.

### Case 8: 00ecc12918ef92739f5306f36eaceb9c.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_8",
    "elementId": "pdf_8_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\00ecc12918ef92739f5306f36eaceb9c.pdf",
    "sourceSha256": "0b80b9e04d44cb2762bceb73b715f29ac41b8f1524b2a295d4c18792051ea140",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_08_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:08:19+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.

### Case 9: 013b1b5f984c80792444bf226d3f2163.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_9",
    "elementId": "pdf_9_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\013b1b5f984c80792444bf226d3f2163.pdf",
    "sourceSha256": "30542471fafcda610606c6a0b77d4d42df86d59421965d17c9fa223883f1189d",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_09_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:08:21+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.

### Case 10: 0168023ef6758a93aad74910f554ab0e.pdf

```json
{
  "schemaVersion": 1,
  "source": {
    "recordId": "pdf_10",
    "elementId": "pdf_10_page_1_clip_1",
    "pdfPath": "Workspace\\data\\downloads\\pdfs\\lithium-sulfur batteries_9400fa3b9d\\0168023ef6758a93aad74910f554ab0e.pdf",
    "sourceSha256": "7cb4564951f0917d374b37a360e8e5dd26c9e000710fd2585f158f9992957f0e",
    "page": 0,
    "figureImagePath": "Workspace\\chart_digitizer_pdf_study\\rendered_pages\\pdf_10_page_001_clip_01.png",
    "caption": ""
  },
  "analysis": {
    "chartType": "unsupported",
    "createdAt": "2026-07-12T21:08:22+00:00",
    "engine": "omnilit_chart_digitizer",
    "sampleCount": 10,
    "confidence": 0.0,
    "eligible": false,
    "needsReview": false,
    "status": "已跳过（不符合曲线图分析条件）",
    "warnings": [
      "未检测到成对且连续的坐标轴，已跳过图数据分析。"
    ],
    "pipeline": [
      {
        "stage": "axis_gate",
        "status": "rejected"
      },
      {
        "stage": "subplot_split",
        "status": "blocked"
      },
      {
        "stage": "axis_calibration",
        "status": "blocked"
      },
      {
        "stage": "curve_sampling",
        "status": "blocked"
      },
      {
        "stage": "data_export",
        "status": "blocked"
      }
    ]
  },
  "subplots": []
}
```

Conclusion: Not yet a reliable chart candidate.
