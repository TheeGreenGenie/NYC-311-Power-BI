# Environment Setup: NYC_311

This guide sets up the Python environment for the data pipeline. Do it once, before running anything in `python\`. It follows the same steps as `Fraud_Detection`, with a new venv name and a much shorter package list.

---

## 1. What you're creating, and where

| Item | Location | What it is |
|---|---|---|
| Project folder | `C:\Users\sgama\Desktop\Data_Analysis_Projects\NYC_311\` | Everything for this project lives here |
| Virtual environment | `...\NYC_311\NYC311Venv\` | A private copy of Python used only by this project |
| Package list | `...\NYC_311\requirements.txt` | The 3 packages to install into `NYC311Venv` |

> `NYC311Venv/` is in `.gitignore`, so it never goes to GitHub. The 311 API needs no key or account.

---

## 2. Step-by-step

### Step 1: Open a PowerShell terminal in the project folder
In VS Code: *Terminal → New Terminal*, then:
```powershell
cd "C:\Users\sgama\Desktop\Data_Analysis_Projects\NYC_311"
```
Check it: `ls` should show `data`, `docs`, `powerbi`, `python` and `requirements.txt`.

### Step 2: Create the venv (Python 3.13)
```powershell
py -3.13 -m venv NYC311Venv
```
It takes 10–20 seconds and prints nothing when it succeeds.
Check it: `ls NYC311Venv` shows `Include`, `Lib`, `Scripts` and `pyvenv.cfg`.

### Step 3: Activate the venv
```powershell
.\NYC311Venv\Scripts\Activate.ps1
```
Your prompt now starts with `(NYC311Venv)`.

> **Every new terminal starts deactivated.** Repeat Steps 1 and 3 each time you open a new terminal for this project. Type `deactivate` to leave the venv.

### Step 4: Confirm you're in the right Python
```powershell
python -c "import sys; print(sys.version); print(sys.executable)"
```
Expected: a version starting with `3.13`, and a path ending in `NYC_311\NYC311Venv\Scripts\python.exe`.
If the path shows `FraudVenv`, `ExcelVenv` or `AppData\Local\Programs\Python`, run `deactivate` and repeat Step 3.

### Step 5: Upgrade pip and install the packages
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```
This takes under a minute.

| Package | What it does in this project |
|---|---|
| `sodapy` | The official Python client for Socrata, the platform behind NYC Open Data. It pulls the 311 requests from the API in pages. |
| `pandas` | Cleans the data, works out response times, and builds the fact and dimension tables Power BI reads |
| `pyarrow` | Saves the raw pull as a compact Parquet file, which loads about 10× faster than CSV |
### Step 6: Verify the install
```powershell
python -c "import sodapy, pandas, pyarrow; print('pandas', pandas.__version__, '| pyarrow', pyarrow.__version__); print('OK')"
```
Expected: one line of version numbers, then `OK`.
`ModuleNotFoundError` means the venv isn't active, or Step 5 didn't finish.

---

## 3. Quick troubleshooting
| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | The venv isn't active (no `(NYC311Venv)` in the prompt). Run Step 3. |
| `pip` installs to the wrong place | Use `python -m pip install -r requirements.txt` |
| "running scripts is disabled" on Activate | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, answer `Y`, and activate again |
| You want a clean slate | `deactivate`, delete `NYC311Venv`, and repeat Steps 2–6 |

---

**When you're done:** run the pipeline: `python python\01_fetch.py`, then `python python\02_transform.py`, then `python python\verify.py`.
