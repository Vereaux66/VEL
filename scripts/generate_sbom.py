#!/usr/bin/env python3
"""
VEL SBOM Generator
==================

Generate Software Bill of Materials (SBOM) for VEL dependencies.
Supports CycloneDX and SPDX formats.

Usage:
    python scripts/generate_sbom.py --format cyclonedx --output sbom.json
    python scripts/generate_sbom.py --format spdx --output sbom.spdx.json
"""

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def get_installed_packages() -> List[Dict[str, Any]]:
    """Get list of installed packages with metadata."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Error getting package list: {result.stderr}", file=sys.stderr)
        return []
    
    packages = json.loads(result.stdout)
    
    # Get detailed info for each package
    detailed_packages = []
    for pkg in packages:
        info = get_package_info(pkg["name"])
        if info:
            detailed_packages.append(info)
    
    return detailed_packages


def get_package_info(package_name: str) -> Optional[Dict[str, Any]]:
    """Get detailed package information."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", package_name],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        logger.warning(f"Failed to get info for package {package_name}: {result.stderr.strip()}")
        return None
    
    info = {}
    for line in result.stdout.strip().split("\n"):
        if ": " in line:
            key, value = line.split(": ", 1)
            info[key.lower().replace("-", "_")] = value
    
    return info


def generate_cyclonedx_sbom(packages: List[Dict[str, Any]], project_name: str = "VEL") -> Dict[str, Any]:
    """Generate CycloneDX format SBOM."""
    components = []
    
    for pkg in packages:
        component = {
            "type": "library",
            "name": pkg.get("name", "unknown"),
            "version": pkg.get("version", "unknown"),
            "purl": f"pkg:pypi/{pkg.get('name', 'unknown')}@{pkg.get('version', 'unknown')}",
        }
        
        if pkg.get("license"):
            component["licenses"] = [{"license": {"name": pkg["license"]}}]
        
        if pkg.get("home_page"):
            component["externalReferences"] = [{
                "type": "website",
                "url": pkg["home_page"]
            }]
        
        if pkg.get("author"):
            component["author"] = pkg["author"]
        
        components.append(component)
    
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{
                "vendor": "VEL",
                "name": "vel-sbom-generator",
                "version": "1.0.0"
            }],
            "component": {
                "type": "application",
                "name": project_name,
                "version": "1.0.0"
            }
        },
        "components": components
    }
    
    return sbom


def generate_spdx_sbom(packages: List[Dict[str, Any]], project_name: str = "VEL") -> Dict[str, Any]:
    """Generate SPDX format SBOM."""
    spdx_packages = []
    
    for i, pkg in enumerate(packages):
        spdx_pkg = {
            "SPDXID": f"SPDXRef-Package-{i}",
            "name": pkg.get("name", "unknown"),
            "versionInfo": pkg.get("version", "unknown"),
            "downloadLocation": pkg.get("home_page", "NOASSERTION"),
            "filesAnalyzed": False,
            "licenseConcluded": pkg.get("license", "NOASSERTION"),
            "licenseDeclared": pkg.get("license", "NOASSERTION"),
            "copyrightText": "NOASSERTION",
            "externalRefs": [{
                "referenceCategory": "PACKAGE_MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:pypi/{pkg.get('name', 'unknown')}@{pkg.get('version', 'unknown')}"
            }]
        }
        spdx_packages.append(spdx_pkg)
    
    relationships = []
    for i in range(len(packages)):
        relationships.append({
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": f"SPDXRef-Package-{i}"
        })
    
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": project_name,
        "documentNamespace": f"https://spdx.org/spdxdocs/{project_name}-{uuid.uuid4()}",
        "creationInfo": {
            "created": datetime.now(timezone.utc).isoformat(),
            "creators": ["Tool: vel-sbom-generator-1.0.0"]
        },
        "packages": spdx_packages,
        "relationships": relationships
    }
    
    return sbom


def main():
    parser = argparse.ArgumentParser(description="Generate SBOM for VEL dependencies")
    parser.add_argument(
        "--format", "-f",
        choices=["cyclonedx", "spdx"],
        default="cyclonedx",
        help="SBOM format (default: cyclonedx)"
    )
    parser.add_argument(
        "--output", "-o",
        default="sbom.json",
        help="Output file path (default: sbom.json)"
    )
    parser.add_argument(
        "--project-name",
        default="VEL",
        help="Project name for SBOM metadata"
    )
    
    args = parser.parse_args()
    
    print(f"Collecting package information...")
    packages = get_installed_packages()
    print(f"Found {len(packages)} packages")
    
    if args.format == "cyclonedx":
        sbom = generate_cyclonedx_sbom(packages, args.project_name)
    else:
        sbom = generate_spdx_sbom(packages, args.project_name)
    
    output_path = Path(args.output)
    output_path.write_text(json.dumps(sbom, indent=2))
    
    print(f"SBOM generated: {output_path}")
    print(f"Format: {args.format.upper()}")
    print(f"Components: {len(packages)}")


if __name__ == "__main__":
    main()
