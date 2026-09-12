from setuptools import setup

with open("README.md") as f:
    long_description = f.read()

setup(
    name="gutenberg_cleaner",
    install_requires=[],
    version="0.2.0",
    description="Clean Project Gutenberg books with conservative rules",
    author="Peyman Mohseni Kiasari",
    author_email="mohsenikiasari@ce.sharif.edu",
    packages=["_cleaning_options"],
    py_modules=["gutenberg_cleaner"],
    url="https://github.com/cassidyhhaas/gutenberg_cleaner_updated",
    license="MIT",
    long_description=long_description,
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
