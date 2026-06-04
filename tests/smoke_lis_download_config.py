from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Download import literature_download_core as core


def main() -> None:
    config = core.CrawlConfig(
        email="qa@example.com",
        out_dir=Path("Download") / "pdfs",
        keywords=["lithium-sulfur batteries", "polysulfides"],
        sources=["openalex", "crossref", "doaj"],
        oa_only=True,
        topic_pack="auto",
        journal_pack="auto",
        min_topic_score=6,
        journal_whitelist_only=False,
        download_pdfs=False,
        max_records=5,
    )
    core.validate_config(config)


if __name__ == "__main__":
    main()
