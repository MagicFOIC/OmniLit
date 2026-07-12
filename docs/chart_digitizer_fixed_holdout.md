# Chart digitizer fixed holdout

The original validation report selected its ten validation samples by the current algorithm score. That made the sample set change whenever the algorithm changed and overstated the chart review rate.

The original ten rendered images are now frozen as a local regression set. Manual inspection showed that they are tables, body-text/reference pages, microscopy/schematic panels, or other images without a usable pair of coordinate axes. They must be skipped rather than sent to chart calibration.

| Metric | Original behavior | Current behavior |
| --- | ---: | ---: |
| Samples | 10 | 10 |
| Sent to review | 6 | 0 |
| Review rate | 60% | 0% |
| Correctly rejected as non-chart | 4 | 10 |

The fixed cases are exercised by `tests/test_chart_digitizer_real_holdout.py` when the local PDF-study images are available. Separately, the adaptive PDF study remains useful for discovering new difficult chart cases, but its changing sample set must not be used for before/after rate comparisons.
