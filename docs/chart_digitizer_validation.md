# Chart Digitizer Validation

This validation section uses local PDFs as a holdout scan. Metrics are automatic QA indicators unless hand-labeled expected points are added later.

| Metric | Current value |
| --- | ---: |
| Automatic recognition rate | 100.0% |
| Subplot split rate | 20.0% |
| Axis calibrated rate | 70.0% |
| Series extracted rate | 100.0% |
| Needs review rate | 60.0% |

| # | PDF name | Figure page | Chart type | Subplots | Series | Axis source | Needs review | Failure attribution | Next fix |
| ---: | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |
| 1 | 0196d51222df996ccdc4ee89a29b3fd2.pdf | 3 | line_chart | 3 | 3 | auto_geometry_preview | yes | axis values need manual/PDF-text calibration | add OCR/manual tick calibration |
| 2 | 00bf712842ac0835e17fed73971157eb.pdf | 3 | line_chart | 4 | 4 | auto_geometry_preview | yes | axis values need manual/PDF-text calibration | add OCR/manual tick calibration |
| 3 | 0179a377ce9afff9a621b33ac5f98666.pdf | 2 | line_chart | 1 | 1 | pdf_text | no | none | add hand-labeled ground truth for point error |
| 4 | 01e19c7823e11ace3057b6fffae25dc0.pdf | 1 | line_chart | 1 | 1 | pdf_text | no | none | add hand-labeled ground truth for point error |
| 5 | 019f758d5b7f249f4bb82353b3c322db.pdf | 2 | line_chart | 1 | 1 | pdf_text | no | none | add hand-labeled ground truth for point error |
| 6 | 00c08eb420b9f04a1e5dc4e0e424ade8.pdf | 3 | line_chart | 1 | 1 | pdf_text | no | none | add hand-labeled ground truth for point error |
| 7 | 013b1b5f984c80792444bf226d3f2163.pdf | 1 | line_chart | 1 | 1 | pdf_text | yes | 坐标轴自动识别置信度较低。; 需要手动校准。 | manual review or calibration |
| 8 | 027af2704caccee4fba6c9f681645261.pdf | 3 | line_chart | 1 | 6 | pdf_text | yes | 坐标轴自动识别置信度较低。; 需要手动校准。 | manual review or calibration |
| 9 | 0168023ef6758a93aad74910f554ab0e.pdf | 4 | line_chart | 1 | 6 | pdf_text | yes | 坐标轴自动识别置信度较低。; 需要手动校准。 | manual review or calibration |
| 10 | 0269871d0d2fd7c869ae783f43ed1bd6.pdf | 3 | line_chart | 1 | 6 | auto_geometry_preview | yes | axis values need manual/PDF-text calibration | add OCR/manual tick calibration |

## Failure Samples

### Validation 1: 0196d51222df996ccdc4ee89a29b3fd2.pdf

- Page: 3
- Result: success
- Warnings: PDF 文本层未能可靠匹配 y 轴两个刻度。; 需要手动校准。

### Validation 2: 00bf712842ac0835e17fed73971157eb.pdf

- Page: 3
- Result: success
- Warnings: 坐标轴识别置信度低，需要手动校准。

### Validation 3: 0179a377ce9afff9a621b33ac5f98666.pdf

- Page: 2
- Result: success
- Warnings: 坐标轴自动识别置信度较低。

### Validation 4: 01e19c7823e11ace3057b6fffae25dc0.pdf

- Page: 1
- Result: success
- Warnings: 坐标轴自动识别置信度较低。

### Validation 5: 019f758d5b7f249f4bb82353b3c322db.pdf

- Page: 2
- Result: success
- Warnings: 坐标轴自动识别置信度较低。

### Validation 6: 00c08eb420b9f04a1e5dc4e0e424ade8.pdf

- Page: 3
- Result: success
- Warnings: 坐标轴自动识别置信度较低。

### Validation 7: 013b1b5f984c80792444bf226d3f2163.pdf

- Page: 1
- Result: success
- Warnings: 坐标轴自动识别置信度较低。; 需要手动校准。

### Validation 8: 027af2704caccee4fba6c9f681645261.pdf

- Page: 3
- Result: success
- Warnings: 坐标轴自动识别置信度较低。; 需要手动校准。

### Validation 9: 0168023ef6758a93aad74910f554ab0e.pdf

- Page: 4
- Result: success
- Warnings: 坐标轴自动识别置信度较低。; 需要手动校准。

### Validation 10: 0269871d0d2fd7c869ae783f43ed1bd6.pdf

- Page: 3
- Result: success
- Warnings: 坐标轴自动识别置信度较低。; 坐标轴识别置信度低，需要手动校准。
