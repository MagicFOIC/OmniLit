# Chart Digitizer Validation

This validation section uses local PDFs as a holdout scan. Metrics are automatic QA indicators unless hand-labeled expected points are added later.

| Metric | Current value |
| --- | ---: |
| Automatic recognition rate | 50.0% |
| Subplot split rate | 30.0% |
| Axis calibrated rate | 30.0% |
| Series extracted rate | 50.0% |
| Needs review rate | 40.0% |

| # | PDF name | Figure page | Chart type | Subplots | Series | Axis source | Needs review | Failure attribution | Next fix |
| ---: | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |
| 1 | 0179a377ce9afff9a621b33ac5f98666.pdf | 1 | line_chart | 2 | 2 | auto_geometry_preview | yes | axis values need manual/PDF-text calibration | add OCR/manual tick calibration |
| 2 | 0196d51222df996ccdc4ee89a29b3fd2.pdf | 1 | unsupported | 0 | 0 | not detected | no | not recognized as line/curve chart | add OCR/manual tick calibration |
| 3 | 019b03a3f5ad34f4b8b9d94ee8f6d020.pdf | 3 | line_chart | 1 | 6 | normalized_arbitrary_units, rapidocr | yes | 需要手动校准。 | manual review or calibration |
| 4 | 019f758d5b7f249f4bb82353b3c322db.pdf | 4 | line_chart | 1 | 6 | normalized_arbitrary_units, rapidocr | no | none | add hand-labeled ground truth for point error |
| 5 | 01dab4903eeba8163c85cb3be580c75f.pdf | 1 | unsupported | 0 | 0 | not detected | no | not recognized as line/curve chart | add OCR/manual tick calibration |
| 6 | 01e19c7823e11ace3057b6fffae25dc0.pdf | 3 | line_chart | 6 | 34 | image_template_ocr, normalized_arbitrary_units, pdf_text, shared_subplot_axis | yes | PDF 文本层未能可靠匹配 y 轴两个刻度。; 需要手动校准。 | manual review or calibration |
| 7 | 01eadb346d60e0bf640cbbaabbc5708b.pdf | 1 | unsupported | 0 | 0 | not detected | no | not recognized as line/curve chart | add OCR/manual tick calibration |
| 8 | 01f089b279cfc27320a8838ac328331a.pdf | 5 | line_chart | 10 | 37 | auto_geometry_preview, image_template_ocr, normalized_arbitrary_units, rapidocr, rapidocr_enlarged, shared_subplot_axis | yes | axis values need manual/PDF-text calibration | add OCR/manual tick calibration |
| 9 | 0209cc71ea9131cb6ac62cd7f0e42138.pdf | 1 | unsupported | 0 | 0 | not detected | no | not recognized as line/curve chart | add OCR/manual tick calibration |
| 10 | 0236c5ce4c082e56a4a631198b6705a2.pdf | 1 | unsupported | 0 | 0 | not detected | no | not recognized as line/curve chart | add OCR/manual tick calibration |

## Failure Samples

### Validation 1: 0179a377ce9afff9a621b33ac5f98666.pdf

- Page: 1
- Result: success
- Warnings: PDF 文本层未能可靠匹配 x 轴两个刻度。; 需要手动校准。

### Validation 2: 0196d51222df996ccdc4ee89a29b3fd2.pdf

- Page: 1
- Result: needs review
- Warnings: 未检测到成对且连续的坐标轴，已跳过图数据分析。

### Validation 3: 019b03a3f5ad34f4b8b9d94ee8f6d020.pdf

- Page: 3
- Result: success
- Warnings: 需要手动校准。

### Validation 4: 019f758d5b7f249f4bb82353b3c322db.pdf

- Page: 4
- Result: success
- Warnings: none

### Validation 5: 01dab4903eeba8163c85cb3be580c75f.pdf

- Page: 1
- Result: needs review
- Warnings: 未检测到成对且连续的坐标轴，已跳过图数据分析。

### Validation 6: 01e19c7823e11ace3057b6fffae25dc0.pdf

- Page: 3
- Result: success
- Warnings: PDF 文本层未能可靠匹配 y 轴两个刻度。; 需要手动校准。

### Validation 7: 01eadb346d60e0bf640cbbaabbc5708b.pdf

- Page: 1
- Result: needs review
- Warnings: 未检测到成对且连续的坐标轴，已跳过图数据分析。

### Validation 8: 01f089b279cfc27320a8838ac328331a.pdf

- Page: 5
- Result: success
- Warnings: PDF 文本层未能可靠匹配 y 轴两个刻度。; 未能可靠分离曲线，需要手动选择曲线或颜色。; 需要手动校准。

### Validation 9: 0209cc71ea9131cb6ac62cd7f0e42138.pdf

- Page: 1
- Result: needs review
- Warnings: 未检测到成对且连续的坐标轴，已跳过图数据分析。

### Validation 10: 0236c5ce4c082e56a4a631198b6705a2.pdf

- Page: 1
- Result: needs review
- Warnings: 未检测到成对且连续的坐标轴，已跳过图数据分析。
