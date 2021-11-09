from distutils.core import setup

from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="folioclient",
    packages=["folioclient"],
    version="0.33",
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    description="A simple wrapper over the FOLIO LMS system API:s",
    author="Theodor Tolstoy",
    author_email="pypi.teddes@tolstoy.se",
    url="https://github.com/FOLIO-FSE/FolioClient/",
    download_url="https://github.com/FOLIO-FSE/FolioClient/archive/v_032.tar.gz",
    keywords=["FOLIO", "FOLIO_LSP", "OKAPI", "API Wrapper"],
    install_requires=["requests"],  # I get to this in a second
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
    ],
)
