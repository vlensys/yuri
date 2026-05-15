from setuptools import setup, find_packages

setup(
    name="yuri-cli",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.9",
    scripts=["yuri"],
    description="Terminal manga/anime reader — yuri genre only.",
)
