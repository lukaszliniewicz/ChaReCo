from setuptools import setup, find_packages

setup(
    name="chareco",
    version="0.3",
    packages=find_packages(),
    install_requires=[
        "PyQt6",
        "dulwich",
        "tiktoken",
        "jupytext"
    ],
    entry_points={
        "console_scripts": [
            "chareco=chareco.app:main",
        ],
    },
    author="Lukasz Liniewicz",
    author_email="l.liniewicz@gmail.com",
    url="https://github.com/lukaszliniewicz/ChaReCo.git",
    python_requires=">=3.8, <3.14",
)

#