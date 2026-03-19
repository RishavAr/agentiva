from pathlib import Path

from setuptools import find_packages, setup


def _read_requirements() -> list[str]:
    requirements_path = Path(__file__).parent / "requirements.txt"
    lines = requirements_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


setup(
    name="agentshield",
    version="0.1.0",
    description="Preview deployments for AI agents",
    license="Apache-2.0",
    python_requires=">=3.10",
    packages=find_packages(),
    include_package_data=True,
    install_requires=_read_requirements(),
    data_files=[("policies", ["policies/default.yaml"])],
    entry_points={
        "console_scripts": [
            "agentshield=agentshield.cli:main",
            "agentshield-server=agentshield.cli:main",
        ]
    },
)
