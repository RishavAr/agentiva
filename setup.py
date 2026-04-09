from pathlib import Path

from setuptools import find_packages, setup


def _read_requirements() -> list[str]:
    requirements_path = Path(__file__).parent / "requirements.txt"
    lines = requirements_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


setup(
    name="agentiva",
    version="0.1.5",
    description="Runtime safety for AI agents: intercept tool calls, policy scoring, and audit logging",
    license="Apache-2.0",
    python_requires=">=3.10",
    packages=find_packages(
        exclude=["tests*", "benchmarks*", "examples*", "demo*", "dashboard*", "website*"],
    ),
    include_package_data=True,
    package_data={"agentiva": ["policies/*.yaml"]},
    install_requires=_read_requirements(),
    extras_require={
        # Recognized third-party benchmark frameworks (optional).
        # Note: `pyrit` is intentionally excluded here because it can conflict with strict pins
        # in this repo depending on versions. Our benchmark runner will still skip gracefully.
        "benchmarks": [
            "deepteam",
            "garak",
        ],
    },
    data_files=[("policies", ["policies/default.yaml"])],
    entry_points={
        "console_scripts": [
            "agentiva=agentiva.cli:main",
            "agentiva-server=agentiva.cli:main",
        ]
    },
)
