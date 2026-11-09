# Xbox FTP Manager

An Android-friendly FTP file manager for Xbox 360 RGH/JTAG consoles running Aurora Dashboard.

Manage Xbox storage directly from an Android phone using Termux, Python and a web browser.

## Features

- Xbox FTP connection and connection testing
- Xbox storage file browser
- Android phone storage browser
- Select individual files or entire folders
- Upload files and folders to Xbox
- Automatic remote folder creation
- Transfer progress monitoring
- Transfer speed and data tracking
- Activity and error reporting
- Stop active transfers

## Project Structure

```text
XboxFTPManager/
├── app.py
├── config.json
├── config.example.json
├── README.md
├── .gitignore
└── static/
    └── index.html
pkg update
pkg install python git
termux-setup-storage
cp config.example.json config.json
cd ~/XboxFTPManager
python app.py

### Then check the files

Once you see the normal `$` prompt again, run:

```bash
git status --short
~/XboxFTPManager $
cd ~/XboxFTPManager

cat > README.md <<'EOF'
# Xbox FTP Manager

An Android-friendly FTP manager for Xbox 360 RGH/JTAG consoles running Aurora Dashboard.

## Features

- Xbox FTP connection testing
- Browse Xbox storage
- Browse Android phone storage
- Select files and folders
- Upload files and folders to Xbox
- Automatic remote folder creation
- Transfer progress and speed monitoring
- Activity and error reporting
- Stop active transfers

## Project Structure

    XboxFTPManager/
    ├── app.py
    ├── config.json
    ├── config.example.json
    ├── README.md
    ├── .gitignore
    └── static/
        └── index.html

## Requirements

- Android phone
- Termux and Python 3
- Xbox 360 RGH/JTAG
- Aurora Dashboard with FTP enabled
- Phone and Xbox on the same local network

## Configuration

Copy the example configuration:

    cp config.example.json config.json

Edit config.json with your own Xbox FTP details.

Never publish your real FTP credentials.

## Start

    cd ~/XboxFTPManager
    python app.py

Open in your Android browser:

    http://127.0.0.1:8765

## Default Upload Destination

    /Hdd1/games

## Project Status

Implemented phone storage browsing, Xbox storage browsing, FTP connection testing, folder selection and upload monitoring.

Large-folder transfer testing is ongoing.

## Security

Keep config.json private. Never publish FTP passwords or expose your Xbox FTP service directly to the public internet.
