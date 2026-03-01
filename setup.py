from setuptools import setup, find_packages

setup(
    name="unibizkit",
    version="0.1.0",
    description="Business Application Generator from JSON Definitions",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="UniBizKit Team",
    author_email="team@unibizkit.org",
    url="https://github.com/unibizkit/unibizkit",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "jsonschema>=4.0.0",
        "typing-extensions>=4.0.0",
    ],
    entry_points={
        "console_scripts": [
            "uni-biz-kit=unibizkit.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)
