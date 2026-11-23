import os

from setuptools import find_namespace_packages, setup

HERE = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="docassamble.fundstructure",
    version="0.1.0",
    description="通过 docassamble 问答生成中基协备案风格的基金架构图（SVG）",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="skillhub",
    license="MIT",
    packages=find_namespace_packages(include=["docassamble.*"]),
    install_requires=[],
    zip_safe=False,
    package_data={
        "docassamble.fundstructure": [
            "data/questions/*",
            "data/static/*",
            "data/sources/*",
            "data/templates/*",
        ]
    },
)
