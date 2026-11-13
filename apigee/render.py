"""Render Apigee proxy bundles and the MCP tool specification."""
import argparse
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SOURCE = Path(__file__).resolve().parent
HOSTNAME = r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"


def write_bundle(path, proxy, placeholder, replacement, resources=()):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as bundle:
        for source in sorted((proxy / "apiproxy").rglob("*.xml")):
            content = source.read_text().replace(placeholder, replacement)
            bundle.writestr(source.relative_to(proxy).as_posix(), content)
        for name, content in resources:
            bundle.writestr(name, content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", required=True, help="Apigee environment-group hostname")
    parser.add_argument("--cloud-run-url", required=True, help="Cloud Run HTTPS service URL")
    parser.add_argument("--organization", help="Apigee organization for the native MCP bundle")
    parser.add_argument("--output", required=True, type=Path, help="Directory for rendered files")
    args = parser.parse_args()
    cloud_run_url = args.cloud_run_url.rstrip("/")
    if not re.fullmatch(HOSTNAME, args.hostname):
        parser.error("--hostname must be a DNS hostname without a scheme or path")
    if not re.fullmatch(rf"https://{HOSTNAME}", cloud_run_url) or not cloud_run_url.endswith(".run.app"):
        parser.error("--cloud-run-url must be the HTTPS run.app service URL without a path")
    if args.organization and not re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", args.organization):
        parser.error("--organization must be an Apigee organization ID")

    args.output.mkdir(parents=True, exist_ok=True)
    rest_proxy = SOURCE / "rest-proxy"
    write_bundle(
        args.output / "order-demo-rest.zip", rest_proxy,
        "https://replace-cloud-run.run.app", cloud_run_url,
    )

    spec = (SOURCE / "order-mcp.yaml").read_text().replace("replace-apigee.example.com", args.hostname)
    (args.output / "order-mcp.yaml").write_text(spec)
    if args.organization:
        verify_policy = rest_proxy / "apiproxy/policies/Verify-Order-Key.xml"
        write_bundle(
            args.output / "order-demo-mcp.zip", SOURCE / "mcp-proxy",
            "replace-apigee-org", args.organization,
            (
                ("apiproxy/policies/Verify-Order-Key.xml", verify_policy.read_text()),
                ("apiproxy/policies/ParsePayload-MCP.xml", (SOURCE / "ParsePayload-MCP.xml").read_text()),
                ("apiproxy/resources/oas/order-mcp.yaml", spec),
            ),
        )


if __name__ == "__main__":
    main()
