from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="valodb",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Valorant Discord Bot for managing accounts and retrieving rank information",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/valodb",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "discord.py==2.3.2",
        "flask==2.3.3",
        "valo_api==2.1.0",
        "gspread==5.12.1",
        "oauth2client==4.1.3",
        "PyNaCl==1.5.0",
        "python-dotenv==1.0.1",
        "zoneinfo; python_version < '3.9'",  # For Python < 3.9
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "valodb=app.main:main",
        ],
    },
) 