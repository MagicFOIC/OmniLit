from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CloudApiDeploymentTests(unittest.TestCase):
    def test_docker_context_excludes_the_local_update_signing_key(self) -> None:
        ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".release", ignored)

    def test_public_web_proxy_does_not_expose_internal_metrics(self) -> None:
        nginx = (ROOT / "deploy/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("location ^~ /internal/", nginx)
        internal = nginx.split("location ^~ /internal/", 1)[1].split("}", 1)[0]
        self.assertIn("return 404", internal)
        self.assertNotIn("proxy_pass", internal)

    def test_compose_uses_a_private_cloud_port_and_separate_metrics_secret(self) -> None:
        compose = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
        cloud = compose.split("\n  cloud-api:\n", 1)[1].split("\n  postgres:\n", 1)[0]
        self.assertTrue('expose:\n      - "8787"' in cloud or 'expose: ["8787"]' in cloud)
        self.assertNotIn("ports:", cloud)
        self.assertIn("OMNILIT_CLOUD_METRICS_TOKEN_FILE", cloud)
        self.assertIn("cloud_metrics_token", cloud)
        self.assertIn("omnilit/cloud-api:${OMNILIT_APP_VERSION:-0.1.0}", cloud)

    def test_all_first_party_deployment_images_are_versioned_as_desktop_release(self) -> None:
        compose = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
        for image in ("web", "cloud-api", "backup"):
            self.assertIn(f"image: omnilit/{image}:${{OMNILIT_APP_VERSION:-0.1.0}}", compose)
        self.assertIn("OMNILIT_APP_VERSION=0.1.0", (ROOT / "deploy/.env.example").read_text(encoding="utf-8"))

    def test_alert_rules_cover_availability_errors_latency_backup_and_capacity(self) -> None:
        rules = (ROOT / "deploy/monitoring/alerts.yml").read_text(encoding="utf-8")
        for alert in (
            "OmniLitCloudApiUnavailable",
            "OmniLitCloudApiNotReady",
            "OmniLitCloudApiHighErrorRate",
            "OmniLitCloudApiHighLatency",
            "OmniLitCloudBackupFailing",
            "OmniLitCloudBackupStale",
            "OmniLitCollaborationStreamsSaturated",
        ):
            self.assertIn(f"alert: {alert}", rules)
        prometheus = (ROOT / "deploy/monitoring/prometheus.yml").read_text(encoding="utf-8")
        self.assertIn("credentials_file: /run/secrets/cloud_metrics_token", prometheus)
        self.assertIn("metrics_path: /internal/metrics", prometheus)


if __name__ == "__main__":
    unittest.main()
