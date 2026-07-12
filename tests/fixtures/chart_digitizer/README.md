# Chart Digitizer Fixtures

Synthetic PNG fixtures for chart digitizer tests are generated inside the unit tests so binary assets do not need to be committed. Real literature PDFs should stay outside git and can be referenced by a local manifest in future validation work.

The synthetic validation baseline is generated at runtime by `omnilit_qt.chart_digitizer_validation`.

```powershell
$env:PYTHONIOENCODING='utf-8'
conda run -n OmniLit python -m omnilit_qt.chart_digitizer_validation --synthetic --out docs/chart_digitizer_validation.synthetic.md --json-out docs/chart_digitizer_validation.synthetic.json
```

This produces 10 temporary chart images covering single-line, multi-line, curve, marker-line, multi-subplot, color, gray, grid-heavy, legend, and OCR-hard tick cases. Licensed real PDFs should be configured locally and not committed.

Private real-PDF validation can use `python -m omnilit_qt.chart_digitizer_validation --manifest path/to/local_manifest.json --out path/to/report.md --json-out path/to/report.json`; the manifest should point to locally extracted figure PNGs and optional manual calibration payloads.
