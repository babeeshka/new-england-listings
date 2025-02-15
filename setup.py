# setup.py
from setuptools import setup, find_packages

setup(
    name="new_england_listings",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "beautifulsoup4>=4.9.3",
        "requests>=2.25.1",
        "selenium>=4.0.0",
        "webdriver-manager>=3.5.2",
        "geopy>=2.2.0",
        "notion-client>=1.0.0",
        "PyYAML>=5.4.1",
        "python-dotenv>=0.19.0",
        "webdriver-manager>=3.5.2",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "isort>=5.0",
            "flake8>=3.9",
        ],
    },
    python_requires=">=3.8",
)
