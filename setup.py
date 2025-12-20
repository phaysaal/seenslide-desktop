#!/usr/bin/env python
"""
SeenSlide - See it again
Real-time slide navigation for presentations
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="seenslide",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="See it again - Real-time slide navigation for presentations",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/seenslide",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Education",
        "Intended Audience :: Science/Research",
        "Topic :: Multimedia :: Graphics :: Capture :: Screen Capture",
        "Topic :: Office/Business",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.10",
    install_requires=[
        "mss>=9.0.1",
        "Pillow>=10.0.0",
        "imagehash>=4.3.1",
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "python-multipart>=0.0.6",
        "websockets>=12.0",
        "customtkinter>=5.2.0",
        "sqlalchemy>=2.0.0",
        "pyyaml>=6.0.1",
        "python-dotenv>=1.0.0",
        "coloredlogs>=15.0.1",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-asyncio>=0.21.0",
            "pytest-mock>=3.12.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
            "isort>=5.12.0",
        ],
        "llm": [
            "openai>=1.3.0",
            "anthropic>=0.7.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "seenslide-admin=modules.admin.main:main",
            "seenslide-server=modules.server.main:main",
            "seenslide-capture=modules.capture.daemon:main",
        ],
    },
    include_package_data=True,
    package_data={
        "modules.server": ["static/*"],
        "": ["config/*.yaml"],
    },
    keywords="presentation slides screen-capture navigation conference seenslide",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/seenslide/issues",
        "Source": "https://github.com/yourusername/seenslide",
        "Documentation": "https://github.com/yourusername/seenslide/docs",
    },
)
