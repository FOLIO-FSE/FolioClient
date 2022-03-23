from distutils.core import setup

setup(
    name="folioclient",
    packages=["folioclient"],
    version="0.39",
    license="MIT",
    long_description="",
    long_description_content_type="text/markdown",
    description="A simple wrapper over the FOLIO LMS system API:s",
    author="Theodor Tolstoy",
    author_email="pypi.teddes@tolstoy.se",
    url="https://github.com/FOLIO-FSE/FolioClient/",
    download_url="https://github.com/FOLIO-FSE/FolioClient/archive/v_039.tar.gz",
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
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
