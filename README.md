<div style="display: flex; align-items: center;">
  <img src="https://github.com/berkucuk/SentinAI/blob/main/icons/icon.png?raw=true" alt="SentinAI Logosu" width="130" style="margin-right: 15px;">
  <h1>SentinAI: AI-Powered Cybersecurity Assistant</h1>
</div>

  **SentinAI** is a modern desktop application developed with PyQt6. It leverages Google Gemini AI models to perform two fundamental cybersecurity tasks: generating realistic password lists based on personal information (PassGen) and gathering open-source intelligence (OSINT). The application features a user-friendly interface with multi-language support (English, Turkish, Russian).

⚠️ Disclaimer

This project is intended strictly for educational purposes and for legal security research, such as penetration testing on authorized systems only.

The use of this application for any illegal or malicious activities is strictly prohibited. All legal and ethical responsibility arising from the use of this tool rests solely with the user. The developer assumes no liability and is not responsible for any misuse or damage caused by this program.

<div style="display: flex; align-items: center;">
  <img src="https://raw.githubusercontent.com/berkucuk/SentinAI/refs/heads/main/Ui.png" alt="SentinAI Ui" width="430" style="margin-right: 15px;">
</div>

## Project Goal

This project aims to provide a powerful and accessible toolkit for cybersecurity professionals, researchers, and enthusiasts. It combines complex command-line tools with the generative power of Google Gemini AI, presenting them in a single, intuitive interface.

1.  **PassGen Mode:** Creates comprehensive wordlists for social engineering and penetration testing, based on realistic, human-like password patterns tailored to a specific target.
2.  **OSINT Mode:** Automatically gathers, verifies, and compiles publicly available data (social media profiles, documents, etc.) about an individual or username into a structured intelligence report.

## Key Features

  * **Dual-Mode Functionality:**
      * **PassGen:** An AI-powered, realistic password list generator based on personal information (name, birthdate, city, etc.).
      * **OSINT:** Conducts extensive open-source intelligence gathering on a target using a full name, username, and keywords.
  * **AI Integration:** Google Gemini AI is used for critical tasks like data analysis, password derivation, profile verification, and final report generation.
  * **Multi-Language Interface:** Switch between English, Turkish, and Russian on the fly.
  * **Modern and User-Friendly GUI:** A clean and intuitive dark-themed interface designed with PyQt6.
  * **Automated Reporting:** OSINT investigation results, including verified data, are saved as a detailed analysis report in Markdown format.
  * **Asynchronous Operations:** Long-running tasks (OSINT, PassGen) are executed in the background without freezing the interface.
  * **External Tool Integration:** Automatically utilizes popular OSINT tools like `social-analyzer`.
  * **Web Verification:** Uses Selenium to verify the existence and validity of potential profiles found online.

## Installation

### From the Maze repository

**On Maze Linux** the repository is already configured:

```bash
sudo pacman -S sentinai
```

**On Arch Linux and Arch-based distributions**, add the repository once:

1. Import and trust the Maze signing key:

   ```bash
   curl -O https://mazerepo.berkkucukk.com.tr/packages/mazelinux.gpg
   gpg --show-keys --with-fingerprint mazelinux.gpg
   sudo pacman-key --add mazelinux.gpg
   sudo pacman-key --lsign-key 7C4D515A6B930CB04794CEF6147C8159B3E2EE5F
   ```

   The fingerprint `gpg` prints must be `7C4D 515A 6B93 0CB0 4794  CEF6 147C 8159 B3E2 EE5F`.

2. Add the repository to the end of `/etc/pacman.conf`:

   ```ini
   [mazelinux]
   SigLevel = Required DatabaseOptional
   Server = https://mazerepo.berkkucukk.com.tr/packages
   ```

3. Sync and install:

   ```bash
   sudo pacman -Syu sentinai
   ```

Optionally install `mazelinux-keyring` as well; it keeps the signing key up to date through pacman.

Remove with `sudo pacman -Rns sentinai`.

### Build from source

The package is built from this working tree by `build-pkg.sh` and installed with pacman, exactly like the published one:

```bash
sudo pacman -S --needed base-devel git
git clone https://github.com/berk-kucuk/SentinAI.git
cd SentinAI
sudo pacman -S --needed $(bash -c 'source packaging/PKGBUILD; echo "${depends[@]}" "${makedepends[@]}"')
./build-pkg.sh --install
```

Without `--install` the package is only built, into `dist-pkg/`.

`maze-python` (the shared Python runtime) comes from the Maze repository, so add the repository first (steps 1–2 above).

### Configure the API key

The cloud features use Google Gemini, which needs an API key:

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey), sign in and create a key.
2. Run `sentinai` once. It creates `~/.config/sentinai/.env` (mode `0600`).
3. Put the key into that file:

   ```
   GOOGLE_API_KEY="YOUR_API_KEY"
   ```

The profile verification feature in OSINT mode also needs **Firefox** (driven through `geckodriver`, which the package pulls in).

## How to Use

After completing all installation steps, run the following command in the main directory to launch the application:

```bash
python app.py
```

### Understanding the Interface

  * **Language Selection:** Change the interface language from the dropdown menu in the top-right corner.
  * **Mode Selection:** Use the central switch to toggle between **PassGen** and **OSINT** modes.
  * **Input Area:** Enter the relevant data here based on the selected mode. A placeholder text provides an example format for each mode.
  * **Execute Button:** After entering your data, click this button to start the task.
  * **Results Area:** The results of the task will be displayed in this section upon completion.

### Mode Usage Examples

#### 1\. PassGen (Password Generator) Mode

This mode generates potential password combinations based on known details about an individual.

  * **Example Input:**
    ```
    name=John, surname=Smith, birthdate=1995, team=lakers, pet=buddy, min_len=8, max_len=16
    ```
  * **Output:** The generated passwords are displayed in the list within the UI and saved as a `.txt` file in the `wordlists/` directory. You can select a password from the list and copy it to the clipboard using the "Copy Selected" button.

#### 2\. OSINT Tool Mode

This mode conducts open-source research on a target.

  * **Example Input:**
    ```
    John Doe, johndoe99, software developer new york
    ```
  * **Output:** Once the investigation is complete, a detailed intelligence report containing verified profiles, documents, and analysis is displayed in the results area in Markdown format. This report is also saved as a `.md` file in the `osints/` directory.

## ⚙️ How It Works

1.  **Interface (`app.py`):** The main application window based on PyQt6. It takes user input, delegates tasks to background threads, and displays the results in the appropriate format.
2.  **Mode Selection:** The user chooses between PassGen and OSINT modes using the `SimpleSwitch` (`custom_widgets.py`).
3.  **Task Manager (`Worker` Class):** Long-running processes like AI requests and OSINT scans are run on a separate `QThread` to prevent the UI from freezing.
4.  **API and Tool Management (`utils.py`):** Loads the Google API key from the `.env` file and checks if external tools like `social-analyzer` are installed.
5.  **PassGen Logic (`passgenai.py`):**
      * Takes personal information from the user.
      * Sends this information to the Gemini AI with a prompt that includes realistic, human-like password creation patterns.
      * Parses the JSON-formatted password list from the AI's response and saves it to a file.
6.  **OSINT Logic (`osintai.py`):**
      * **Entity Extraction:** Gemini AI extracts entities like `full_name`, `username`, and `keywords` from the user's input.
      * **Data Collection:** It searches for the username with `social-analyzer` and gathers potential URLs using Google Dorking techniques via `googlesearch-python`.
      * **Verification (Selenium):** Each found URL is visited using Selenium and a headless browser (Chrome/Firefox). The page content is then sent to Gemini AI to classify whether it's a genuine user profile or an error/login page.
      * **Reporting:** Only URLs verified as `VALID_PROFILE` are submitted to Gemini AI for final analysis. The AI synthesizes this data into a detailed, evidence-based, and structured intelligence report.

## 🤝 Contributing

Contributions are welcome and will help take this project further\! Please feel free to open a pull request or report an issue. All contributions are welcome, especially for new features, bug fixes, and code improvements.

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
