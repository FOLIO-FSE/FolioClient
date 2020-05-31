from distutils.core import setup


setup(
    name="folioclient",
    packages=["folioclient"],
    version="0.24",
    license="MIT",
    long_description="",
    long_description_content_type="text/markdown",
    description="A simple wrapper over the FOLIO LMS system API:s",
    author="Theodor Tolstoy",
    author_email="pypi.teddes@tolstoy.se",
    url="https://github.com/fontanka16/FolioClient",
    download_url="https://github.com/fontanka16/FolioClient/archive/v_018.tar.gz",
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
